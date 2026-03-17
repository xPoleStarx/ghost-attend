#!/usr/bin/env python3
"""
GhostAttend — Master Key Rotation Script

Mevcut credential'ları eski key ile çözüp yeni key ile şifreler.
Kullanım:
    python scripts/rotate_keys.py --old-key=ESKİ --new-key=YENİ
"""

import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from src.security.encryption import CredentialVault


async def rotate_keys(old_key: str, new_key: str, database_url: str):
    """Tüm credential'ları yeni key ile yeniden şifrele."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from src.db.models import Credential

    old_vault = CredentialVault(old_key)
    new_vault = CredentialVault(new_key)

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(select(Credential))
        credentials = result.scalars().all()

        print(f"📋 {len(credentials)} credential bulundu.")

        success = 0
        failed = 0

        for cred in credentials:
            try:
                # Eski key ile çöz
                email = old_vault.decrypt(cred.user_id, cred.email_enc)
                password = old_vault.decrypt(cred.user_id, cred.password_enc)

                # Yeni key ile şifrele
                cred.email_enc = new_vault.encrypt(cred.user_id, email)
                cred.password_enc = new_vault.encrypt(cred.user_id, password)

                # Cookie varsa onu da rotate et
                if cred.cookie_enc:
                    cookies = old_vault.decrypt_cookies(cred.user_id, cred.cookie_enc)
                    cred.cookie_enc = new_vault.encrypt_cookies(cred.user_id, cookies)

                success += 1

            except Exception as e:
                print(f"❌ user_id={cred.user_id} başarısız: {e}")
                failed += 1

        await session.commit()

    await engine.dispose()

    print(f"\n✅ {success} credential başarıyla rotate edildi.")
    if failed:
        print(f"❌ {failed} credential başarısız oldu.")

    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Master key rotasyonu")
    parser.add_argument("--old-key", required=True, help="Mevcut master key")
    parser.add_argument("--new-key", required=True, help="Yeni master key")
    parser.add_argument(
        "--database-url",
        default=None,
        help="DB URL (default: .env'den)",
    )
    args = parser.parse_args()

    db_url = args.database_url
    if not db_url:
        from src.core.config import settings
        db_url = settings.DATABASE_URL

    success = asyncio.run(rotate_keys(args.old_key, args.new_key, db_url))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
