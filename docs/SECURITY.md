# Güvenlik Politikası

## Mimari Güvenlik

### Credential Saklama
- Tüm şifreler **Fernet + PBKDF2-SHA256** ile şifrelenir
- Her kullanıcı için **user_id'den türetilmiş unique key** kullanılır
- **480.000 PBKDF2 iterasyonu** (OWASP 2024 önerisi)
- Master key `.env`'de saklanır, **asla DB'ye yazılmaz**
- Plaintext şifre **hiçbir yerde** loglanmaz veya saklanmaz

### Telegram Güvenliği
- Kullanıcının şifre mesajı **anında silinir** (Telegram API ile)
- "Şifreni yaz" prompt mesajı da silinir
- MFA kodları da gönderildikten sonra silinir

### Session/Cookie Güvenliği
- Browser cookie'leri şifreli olarak DB'de saklanır
- Cookie expire süreleri takip edilir (varsayılan 30 gün)
- Günlük kontrol ile expire olacak cookie'ler tespit edilir

### Docker Güvenliği
- Tüm container'lar **non-root** kullanıcı ile çalışır
- `.env` dosyası `.gitignore`'da, asla repo'ya commit edilmez
- Network izolasyonu (internal Docker network)

## Bilinen Riskler

> ⚠️ Bu yazılım Microsoft Teams ToS'a ve bazı üniversite yönetmeliklerine
> aykırı olabilir. Kullanıcı tüm yasal sorumluluğu üstlenir.

## Güvenlik Açığı Bildirimi

Güvenlik açığı bulduysanız **public issue açmayın**. Bunun yerine
proje yöneticisine doğrudan ulaşın.

## Master Key Rotasyonu

```bash
# 1. Yeni key üret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. Mevcut credential'ları yeni key ile yeniden şifrele
python scripts/rotate_keys.py --old-key=ESKİ_KEY --new-key=YENİ_KEY

# 3. .env'yi güncelle
MASTER_ENCRYPTION_KEY=yeni-key

# 4. Servisleri yeniden başlat
docker compose restart bot worker
```
