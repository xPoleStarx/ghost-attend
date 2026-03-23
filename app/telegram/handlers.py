from __future__ import annotations

import base64
import logging
from io import BytesIO
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from telegram import Update
from telegram.ext import ContextTypes

from app.adapters.browser_session_holder import kill_session
from app.agent.media_delivery import pop_screenshot_png
from app.agent.output import last_assistant_text_for_telegram
from app.telegram.locks import chat_turn
from app.run_control import (
    clear_stop,
    enqueue_user_correction,
    is_browser_run_active_async,
    register_progress_sender,
    request_stop,
    unregister_progress_sender,
)

logger = logging.getLogger(__name__)

_RECURSION_LIMIT = 120


def _unwrap_interrupts(result: dict[str, Any]) -> list[Any]:
    raw = result.get("__interrupt__")
    if not raw:
        return []
    out: list[Any] = []
    for item in raw:
        val = getattr(item, "value", item)
        out.append(val)
    return out


async def _pending_interrupt(graph: Any, config: dict[str, Any]) -> bool:
    """AsyncSqliteSaver ile senkron get_state kullanılmamalı (ana event loop)."""
    try:
        snap = await graph.aget_state(config)
    except Exception:
        return False
    intr = getattr(snap, "interrupts", None)
    if intr:
        return True
    nxt = getattr(snap, "next", None)
    if nxt:
        return True
    tasks = getattr(snap, "tasks", None)
    if tasks:
        return True
    return False


async def _checkpoint_messages(graph: Any, config: dict[str, Any]) -> list[Any]:
    try:
        snap = await graph.aget_state(config)
        return list(snap.values.get("messages") or [])
    except Exception:
        logger.exception("aget_state failed (checkpoint okunamadı)")
        return []


def _tool_call_id(tc: Any) -> str | None:
    if isinstance(tc, dict):
        tid = tc.get("id") or tc.get("tool_call_id")
    else:
        tid = getattr(tc, "id", None) or getattr(tc, "tool_call_id", None)
    return str(tid) if tid else None


def _has_open_tool_calls(messages: list[Any]) -> bool:
    """Araç içi interrupt sonrası: AIMessage+tool_calls var, ToolMessage eksik — resume şart."""
    pending: set[str] = set()
    for m in messages:
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            for tc in m.tool_calls:
                tid = _tool_call_id(tc)
                if tid:
                    pending.add(tid)
        elif isinstance(m, ToolMessage):
            tid = getattr(m, "tool_call_id", None)
            if tid and str(tid) in pending:
                pending.discard(str(tid))
    return bool(pending)


async def _delete_thread_checkpoint(graph: Any, thread_id: str) -> None:
    """Bozuk checkpoint (yetim tool_calls) için: SQLite/memory thread kaydını tamamen sil."""
    cp = getattr(graph, "checkpointer", None)
    if cp is None:
        return
    fn = getattr(cp, "adelete_thread", None)
    if fn is None:
        return
    await fn(str(thread_id))
    logger.info("Checkpoint thread silindi: %s", thread_id)


async def _send_interrupt_payloads(update: Update, context: ContextTypes.DEFAULT_TYPE, result: dict[str, Any]) -> None:
    chat = update.effective_chat
    if not chat:
        return
    for payload in _unwrap_interrupts(result):
        if not isinstance(payload, dict):
            if payload:
                await context.bot.send_message(chat_id=chat.id, text=str(payload)[:4096])
            continue
        q = payload.get("question") or ""
        png = payload.get("screenshot_png")
        b64 = payload.get("screenshot_png_b64")
        if b64 and not png:
            try:
                png = base64.b64decode(b64)
            except Exception:
                png = None
        if q:
            await context.bot.send_message(chat_id=chat.id, text=str(q)[:4096])
        if png:
            bio = BytesIO(png)
            bio.name = "interrupt.png"
            cap = (payload.get("photo_caption") or "Ekran görüntüsü — yukarıdaki mesajdaki talimatlara göre yanıt ver.")[
                :1024
            ]
            await context.bot.send_photo(chat_id=chat.id, photo=bio, caption=cap)


async def _send_regular_outputs(update: Update, context: ContextTypes.DEFAULT_TYPE, result: dict[str, Any]) -> None:
    chat = update.effective_chat
    if not chat:
        return
    rt = result.get("reply_text")
    if rt:
        await context.bot.send_message(chat_id=chat.id, text=str(rt)[:4096])
    png = result.get("screenshot_png")
    if png and not _unwrap_interrupts(result):
        bio = BytesIO(png)
        bio.name = "page.png"
        await context.bot.send_photo(chat_id=chat.id, photo=bio, caption="Ekran görüntüsü"[:1024])


async def on_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    text = (update.message.text or "").strip()
    if not text:
        return
    chat_id = update.effective_chat.id
    tid = str(chat_id)
    if await is_browser_run_active_async(tid):
        await enqueue_user_correction(tid, text)
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Not alındı. Çalışan tarayıcı görevi bir sonraki adımda duracak ve mesajın "
                "dikkate alınması için sana yanıt isteyecek; oturum açık kalır."
            ),
        )
        return
    graph = context.application.bot_data["graph"]
    config: dict[str, Any] = {"configurable": {"thread_id": str(chat_id)}}

    invoke_cfg = {**config, "recursion_limit": _RECURSION_LIMIT}

    async def _send_progress(text: str) -> None:
        await context.bot.send_message(chat_id=chat_id, text=text[:4096])

    register_progress_sender(str(chat_id), _send_progress)
    async with chat_turn(chat_id):
        try:
            try:
                awaiting = bool(context.chat_data.get("awaiting_resume"))
                chk_msgs = await _checkpoint_messages(graph, config)
                open_tools = _has_open_tool_calls(chk_msgs)
                pending_intr = await _pending_interrupt(graph, config)
                # interrupt() araç ortasında kesildiğinde ToolMessage oluşmaz; yeni HumanMessage geçmişi bozar.
                if open_tools or awaiting or pending_intr:
                    result = await graph.ainvoke(Command(resume=text), invoke_cfg)
                else:
                    result = await graph.ainvoke(
                        {"messages": [HumanMessage(content=text)]},
                        invoke_cfg,
                    )
            except ValueError as e:
                err = str(e)
                if "ToolMessage" in err or "tool_calls" in err or "INVALID_CHAT_HISTORY" in err:
                    logger.warning("Geçersiz sohbet geçmişi (checkpoint); thread siliniyor: chat_id=%s", chat_id)
                    try:
                        # messages=[] yazmak yetmez; add_messages checkpoint ile birleşince yetim AIMessage kalabiliyor.
                        await _delete_thread_checkpoint(graph, str(chat_id))
                        result = await graph.ainvoke(
                            {"messages": [HumanMessage(content=text)]},
                            invoke_cfg,
                        )
                    except Exception:
                        logger.exception("graph.ainvoke retry failed for chat_id=%s", chat_id)
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="İşlem sırasında bir hata oluştu. Biraz sonra tekrar dene.",
                        )
                        return
                else:
                    logger.exception("graph.ainvoke failed for chat_id=%s", chat_id)
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="İşlem sırasında bir hata oluştu. Biraz sonra tekrar dene.",
                    )
                    return
            except Exception:
                logger.exception("graph.ainvoke failed for chat_id=%s", chat_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="İşlem sırasında bir hata oluştu. Biraz sonra tekrar dene.",
                )
                return

            messages = result.get("messages") or []
            intrs = _unwrap_interrupts(result)
            reply_text = last_assistant_text_for_telegram(messages) or ""
            if not reply_text.strip() and not intrs:
                reply_text = "Tamam."
            elif intrs and not reply_text.strip():
                reply_text = ""
            png = pop_screenshot_png(str(chat_id))
            merged: dict[str, Any] = {
                **result,
                "reply_text": reply_text,
                "screenshot_png": png,
            }

            pending_snap = await _pending_interrupt(graph, config)
            context.chat_data["awaiting_resume"] = bool(intrs) or pending_snap
            await _send_interrupt_payloads(update, context, merged)
            await _send_regular_outputs(update, context, merged)
        finally:
            unregister_progress_sender(str(chat_id))


async def on_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tarayıcı otomasyonu sırasında /stop — chat_turn kullanılmaz (kilitlenme olmasın)."""
    if not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    tid = str(chat_id)
    if not await is_browser_run_active_async(tid):
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Şu anda çalışan bir tarayıcı görevi yok. /stop, site üzerinde adım adım ilerleyen "
                "otomasyon sırasında en güvenilir şekilde çalışır; model yalnızca düşünüyorsa duraklama gecikebilir."
            ),
        )
        return
    request_stop(tid)
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "Durdurma istendi. Model yanıtı veya tek bir tarayıcı aksiyonu sürüyorsa birkaç saniye "
            "sürebilir; adımlar arasında kesilir. Görev güvenli şekilde sonlandırılacak."
        ),
    )


async def on_reset_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bu sohbet için LangGraph checkpoint + tarayıcı + bekleyen interrupt durumunu sıfırla."""
    if not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    graph = context.application.bot_data["graph"]

    async with chat_turn(chat_id):
        try:
            clear_stop(str(chat_id))
            await _delete_thread_checkpoint(graph, str(chat_id))
        except Exception:
            logger.exception("reset: checkpoint silinemedi chat_id=%s", chat_id)
        try:
            await kill_session(str(chat_id))
        except Exception:
            logger.exception("reset: kill_session chat_id=%s", chat_id)
        context.chat_data.pop("awaiting_resume", None)
        pop_screenshot_png(str(chat_id))

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "Context reset for this chat: conversation history and task state were cleared, "
            "and the browser session was closed. You can send a fresh request from scratch."
        ),
    )


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "👻 Hey — I'm *GhostMyShit*, your web agent.\n\n"
            "🤖 Tell me what you need in plain language; I run sites *on my own* — navigate, click, fill forms, grab screenshots, "
            "and work through multi-step jobs end-to-end. If something needs a password or 2FA, I'll ask you here.\n\n"
            "⚠️ *Heads-up:* don't manually kill the automation browser window or tab — it can confuse the session. "
            "To close it cleanly, use `/tarayici`.\n\n"
            "🧹 Fresh start (wipes this chat's memory *and* the browser session): `/temizle` or `/reset`\n\n"
            "⏹ *Stop a running browser job:* `/stop` or `/dur` — works best while the site automation is stepping; "
            "if the model is only thinking, it may stop slightly later."
        ),
        parse_mode="Markdown",
    )


async def on_close_browser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Açık Playwright/Chromium oturumunu kapat; sonraki web görevi yeni pencere açar."""
    if not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    try:
        await kill_session(str(chat_id))
    except Exception:
        logger.exception("kill_session failed chat_id=%s", chat_id)
        await context.bot.send_message(chat_id=chat_id, text="Tarayıcı kapatılırken hata oluştu.")
        return
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "Tarayıcı oturumu kapatıldı. Sonraki web görevi yeni bir pencere açar.\n\n"
            "İleride sekmeyi elle kapatmak yerine yine /tarayici kullan; aksi halde logda "
            "'detached / No tabs remain' uyarıları ve takılma oluşabilir."
        ),
    )
