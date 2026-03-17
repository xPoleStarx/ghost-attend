# Senaryo Matrisi

Agent çalışması sırasında karşılaşılabilecek senaryolar ve otomatik kurtarma stratejileri.

## Özet Tablo

| # | Senaryo | Recovery | Max Retry | Delay | Bildirim | Fatal |
|---|---|---|---|---|---|---|
| 1 | ✅ Happy path | Devam | 0 | - | ✅ | ❌ |
| 2 | ❌ DYS login fail | Kullanıcıya bildir | 1 | - | ✅ | ✅ |
| 3 | 🔧 DYS bakımda | Gecikmeli tekrar | 3 | 2dk | ✅ | ❌ |
| 4 | 🔗 Link bulunamadı | Gecikmeli tekrar | 2 | 1dk | ✅ | ❌ |
| 5 | ⏳ Toplantı başlamamış | Bekle + tekrar | 5 | 1dk | ❌ | ❌ |
| 6 | 📱 MFA SMS | Kod iste | 0 | - | ✅ | ❌ |
| 7 | 📱 MFA Authenticator | Onay iste | 0 | - | ✅ | ❌ |
| 8 | ❌ Katılım başarısız | Tekrar dene | 2 | 15sn | ✅ | ❌ |
| 9 | 🧊 Sayfa donması | Tekrar dene | 2 | 10sn | ❌ | ❌ |
| 10 | 🍪 Cookie expired | Yeniden giriş | 1 | - | ❌ | ❌ |
| 11 | 👢 Session kicked | Tekrar dene | 1 | 5sn | ✅ | ❌ |
| 12 | 🌐 Ağ hatası | Gecikmeli tekrar | 5 | 30sn | ✅ | ❌ |

## Detaylı Açıklamalar

### 1. Happy Path
Tüm adımlar başarılı. DYS giriş → Ders bulma → Teams katılım → Ders sonu.

### 2. DYS Login Fail
Şifre yanlış veya hesap kilitli. Kullanıcıya `/reauth` ile güncelleme önerilir. **Fatal** — retry anlamsız.

### 3. DYS Bakım
DYS "bakım modu" sayfası gösteriyor. 2dk arayla 3 kez yeniden dener.

### 4. Link Bulunamadı
Ders sayfasında canlı ders linki yok. Hoca henüz paylaşmamış olabilir. 1dk arayla 2 kez dener.

### 5. Toplantı Başlamamış
Teams/Zoom toplantısı henüz başlatılmamış. Beklenen durum, sessizce 1dk arayla 5 kez dener.

### 6-7. MFA
Agent durur → Telegram'a bildirim → Kullanıcı kod yazar veya Authenticator'ı onaylar → Agent devam eder.
- SMS: 120 saniye timeout
- Authenticator: 60 saniye timeout

### 8. Katılım Başarısız
"Katıl" butonuna tıklandı ama toplantıya girilemedi. 15sn arayla 2 kez dener.

### 9. Sayfa Donması
Tarayıcı yanıt vermiyor. Sayfa yenilenir, 10sn arayla 2 kez dener.

### 10. Cookie Expired
Kayıtlı session cookie süresi dolmuş. Otomatik olarak credential ile yeniden giriş yapar.

### 11. Session Kicked
Başka cihazdan giriş yapıldı veya toplantıdan atıldı. 5sn sonra yeniden bağlanır.

### 12. Ağ Hatası
İnternet bağlantısı koptu. 30sn arayla 5 kez yeniden bağlanmaya çalışır.
