# Katkı rehberi

Teşekkürler. Küçük ve odaklı değişiklikler en kolay birleşir.

## Geliştirme ortamı

1. Depoyu klonlayın, [README.md](README.md) içindeki kurulumu izleyin (tercihen `Run.ps1` / `Run.sh`).
2. `.env` dosyasını **commit etmeyin**; `.env.example` şablonunu kullanın.
3. Test: proje kökünde `python -m pytest` (veya `make test`).

## Pull request

- Tek konuya odaklı PR’lar tercih edilir.
- Mümkünse `pytest` yeşil kalsın.
- API anahtarları, token veya kişisel veri eklemeyin.

## Sorun bildirimi

Hata raparında mümkünse: işletim sistemi, Python sürümü, ilgili `.env` anahtarlarını **değer vermeden** (ör. “Gemini 400” gibi) ve kısa yeniden üretim adımları.
