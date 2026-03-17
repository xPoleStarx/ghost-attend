"""
GhostAttend — Vision LLM Prompt'ları

Tüm LLM prompt'ları burada tanımlanır. Hardcode prompt yok, tek kaynak.
architecture.md Section 8.2
"""

SCHEDULE_PARSE_PROMPT = """
Bu görsel(ler) bir üniversite ders programıdır. Birden fazla görsel veya ek metin bilgisi verilmis olabilir.

GÖREVİN:
Tüm görsel ve metinlerdeki TÜM dersleri tespit et. Aynı ders birden fazla görselde geçiyorsa tekrar etme.

ÖNEMLI KURALLAR:
1. Sadece "Online", "Uzaktan", "Teams", "Zoom", "Meet" gibi ifadeler içeren veya
   derslik bilgisi OLMAYAN dersleri online_mi: true olarak işaretle.
2. "Derslik: A101" gibi fiziksel yer bilgisi olan dersler online_mi: false.
3. Belirsiz durumlar için online_mi: null kullan.
4. Platform tespiti için ders adı, açıklama veya yer bilgisinde
   "Teams", "Zoom", "Meet" ara. Bulamazsan "unknown".
5. Saat formatı her zaman "HH:MM" (24 saat).
6. Güven skoru: Okuyamadığın, bulanık veya kısmi gördüğün alanlar için düşük ver.
7. Gün adlarını Türkçe yaz: Pazartesi, Salı, Çarşamba, Perşembe, Cuma, Cumartesi, Pazar
8. online_mi alanını MUTLAKA true, false veya null olarak doldur. Boş bırakma.

ÇIKTI FORMATI (yalnızca geçerli JSON, markdown code block içinde):
```json
{
  "courses": [
    {
      "ders_adi": "Ders Adı",
      "gun": "Pazartesi",
      "baslangic_saati": "09:00",
      "bitis_saati": "10:30",
      "ogretim_uyesi": "Dr. Ad Soyad",
      "platform": "teams",
      "online_mi": true,
      "guvven_skoru": 0.95
    }
  ],
  "raw_text": "Görselden okunan ham metin...",
  "parse_warnings": ["Uyarı mesajları varsa buraya"]
}
```

KRİTİK: Sadece JSON döndür. Açıklama, yorum veya ek metin ekleme.
"""

SCREEN_ANALYZE_PROMPT = """
Bu bir üniversite DYS (Ders Yönetim Sistemi) veya Teams/Zoom ekran görüntüsüdür.

GÖREVİN:
Ekranda ne gördüğünü analiz et ve aşağıdaki bilgileri JSON olarak döndür.

```json
{
  "page_type": "login | dashboard | course_list | course_detail | meeting_page | error | unknown",
  "description": "Sayfanın kısa açıklaması",
  "action_needed": "Yapılması gereken eylem (tıklanacak buton, girilecek form vs.)",
  "elements": [
    {
      "type": "button | link | input | text",
      "text": "Elemanın metni",
      "action": "click | type | ignore"
    }
  ],
  "warnings": ["Varsa uyarı veya hatalar"]
}
```

Sadece JSON döndür.
"""

MFA_DETECT_PROMPT = """
Bu ekran görüntüsünde bir MFA/2FA (çok faktörlü kimlik doğrulama) ekranı var mı?

Kontrol et:
1. SMS kodu isteniyor mu?
2. Microsoft Authenticator onayı bekleniyor mu?
3. E-posta doğrulama kodu isteniyor mu?
4. Herhangi bir doğrulama sorusu soruluyor mu?

```json
{
  "mfa_detected": true,
  "mfa_type": "sms | authenticator | email | question | none",
  "description": "MFA ekranının açıklaması",
  "input_field_visible": true,
  "action": "Kullanıcıdan kod/onay istenmeli"
}
```

Sadece JSON döndür.
"""
