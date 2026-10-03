# Oxford 3000 · İngilizce Kelime Ezberleme

İngilizcede en sık kullanılan 3000 kelimeyi (Oxford 3000) Türkçe karşılıklarıyla
ezberlemek için masaüstü programı. Tamamen çevrimdışı çalışır, web değildir.

## Kurulum (kullanıcılar için)

1. [**Releases**](https://github.com/Obirize/Oxford-3000-Kelime/releases/latest)
   sayfasından `Oxford3000-Kurulum-x.y.z.exe` dosyasını indir.
2. Çift tıkla, "İleri"ye bas. Yönetici izni istemez; program
   `%LocalAppData%\Programs\Oxford3000` klasörüne kurulur, masaüstüne ve
   Başlat menüsüne kısayol koyar.
3. Aç, kelimeleri yazmaya başla. Python vb. hiçbir şey kurman gerekmez.

> Windows SmartScreen "tanınmayan uygulama" uyarısı verebilir (imzasız küçük
> bir program olduğu için). **Daha fazla bilgi → Yine de çalıştır** de.

İlerlemen kurulum klasöründeki `data\progress.db` dosyasında tutulur; program
her açılış ve kapanışta `data\backups\` altına otomatik yedek alır. Programı
kaldırsan bile ilerleme dosyası silinmez.

**Kurulumsuz kullanmak istersen:** Releases'teki `Oxford3000.exe` tek başına
çalışır; hangi klasöre koyarsan ilerlemeyi yanındaki `data/` klasörüne yazar.
Taşırsan `data/` klasörünü de birlikte taşı.

### İlerlemem nerede? (taşınabilirden kuruluma geçiş)

İlerleme **her zaman exe'nin yanındaki `data/` klasöründedir**. Bu, programı
USB'de taşımayı mümkün kılar ama bir tuzağı vardır: taşınabilir exe ile
çalışıp sonra kurulum paketini kurarsan, kurulu sürüm **başka bir klasörde**
olduğu için bomboş bir ilerlemeyle açılır. Hiçbir şey silinmemiştir, eski
ilerleme eski klasörde durur.

Program bunu kendisi halleder: açılışta burada ilerleme yoksa kendi bilinen
klasörlerine bakar (kurulum klasörü, exe'nin bulunduğu klasör ve bunların
`backups/` klasörleri) ve çalışılmış bir ilerleme bulursa sorar:
*"Buraya kopyalansın mı?"* — Evet dersen kopyalanır, **eski dosyaya
dokunulmaz**. Kullanıcının belgeleri taranmaz; yalnızca bu sabit klasörlere
bakılır (`app/handoff.py`).

Kendin taşımak istersen: eski `data\progress.db` dosyasını yeni kurulumun
`data` klasörüne kopyala, ya da Ayarlar → *Görünüm ve veri* → **Dosyadan geri
yükle** ile seç. Kurulum klasörü:
`%LocalAppData%\Programs\Oxford3000\data`

Telaffuz sesi Google TTS'ten gelir ve internet ister; bir kez duyulan kelime
önbelleğe alınır. Gerisi tamamen çevrimdışıdır.

## Geliştiriciler için

Kaynak koddan çalıştırmak:

```bash
py main.py
```

Kurulum paketi üretmek (Inno Setup 6 gerekir):

```bash
py tools/build_setup.py            # exe + dist/Oxford3000-Kurulum-1.0.0.exe
```

Depoda **olmayanlar** (`.gitignore`): kullanıcı ilerlemesi, yedekler, ses
önbelleği, derlenmiş exe'ler ve veri setinin üretildiği üçüncü taraf ham
kaynaklar (`tools/dict.zip`, `ciwga.csv`, `gist_tr.json`, Oxford PDF'i).
Üretilmiş `data/oxford3000.json` depodadır; program için o yeter.
`build_dataset.py` çalıştırmak istersen kaynakları ayrıca temin etmen gerekir.

## Exe'yi yeniden üretme

Kodda değişiklik yaptıktan sonra:

```bash
py tools/build_exe.py              # ikon + exe üretir, proje köküne kopyalar
py tools/build_exe.py --shortcut   # ayrıca masaüstüne kısayol koyar
```

Üretilen exe ~15 MB, tek dosya, konsol penceresi açmaz. Kelime listesi ve ikon
paketin içine gömülüdür; ilerleme/yedek/ses ise exe'nin yanındaki `data/`
klasörüne yazılır — exe'yi yenilesen bile ilerlemen korunur.

## Gereksinimler

Exe için hiçbir şey gerekmez. Kaynak koddan çalıştırmak veya derlemek için:

- **Python 3.10+** (tkinter ile birlikte gelir — Windows'ta varsayılan kurulu)
- Zorunlu bağımlılık **yok**. Veritabanı, arayüz ve grafikler standart kütüphaneyle.
- İsteğe bağlı: telaffuz için `pip install gTTS`, veri setini yeniden üretmek
  için `pip install pypdf`, exe derlemek için `pip install pyinstaller pillow`.

## Nasıl çalışır

Kelimeler dört durumdan birindedir:

| Durum | Anlamı |
|---|---|
| **Havuzda** | Henüz hiç gösterilmedi |
| **Biliniyor** | İlk gösterimde tek seferde doğru bilindi → bir daha asla çıkmaz |
| **Öğreniliyor** | İlk seferde bilinemedi → tekrar döngüsünde (1000 gösterim bütçesi) |
| **Öğrenildi** | 20 kez üst üste doğru bilindi → rotasyondan çıktı |

### Tekrar merdiveni — asıl öğrenme mekanizması

Bilemediğin kelime kaybolmaz. Genişleyen aralıklarla tekrar tekrar karşına çıkar:

    3 kart sonra → 8 → 20 → 45 → 100 → 250 → 600

Her doğru bir üst basamağa taşır, **her yanlış başa döndürür**. Sözlükten
parmakla kapatarak ezberlemenin dijital karşılığı: önce sık sık, sonra gitgide
seyrek — ama hep geri geliyor.

Kartta o an nerede olduğunu görürsün:
*"3. tekrar · seri 2/20 · bilirsen 20 kart sonra yine sorulacak"*

### Yeni kelime garantisi ve oturum sınırı

Her turda **en az 4 yeni kelime** gelir (havuz bitene dek), kalan 6 yer tekrarı
gelmiş kartlara ayrılır — en gecikmiş olan önce. Tekrar yığını ne kadar
büyürse büyüsün yeni kelime akışı kesilmez.

Aynı kelime **bir oturumda en fazla 3 kez** sorulur; fazlası ertesi oturuma
kalır. Böylece bilemediğin 10 kelime arasında sıkışıp kalmazsın: yanlış →
yazarak pekiştir → 3 kart sonra → 8 kart sonra → yarın.

> Tarihçe: bir ara "aynı anda en fazla 12 kelime öğreniliyor" diye bir aktif
> pencere vardı. Öğreniliyor sayısı 12'yi aşınca (merdiven eklenirken 40 kelime
> içeri alınmıştı) yeni kelime tamamen kesiliyor ve aynı kelimeler dönüp dönüp
> geliyordu. Kaldırıldı; yerini yukarıdaki iki kural aldı. İki ayar da
> Ayarlar'dan değiştirilebilir.

### "Yazarak pekiştir" adımı

Yeni bir kelimeyi bilemediğinde program cevabı gösterip geçmez: doğru cevabı
**bir kez yazmanı** ister. Test edilmeden önceki öğrenme anı — sözlükte
"1'e bakıp okumak" gibi. `Esc` ile atlanabilir, Ayarlar'dan kapatılabilir.

### Bilinen kelimenin teyidi

Tek seferde bildiğin kelime "biliniyor"a gider ama ilerde **bir kez daha**
sorulur. Şansla bilinen kelime kalıcı olarak elenmesin diye. Teyidi geçerse
mühürlenir, geçemezse tekrar merdivenine girer.

**Hibrit ritim.** Bir kelime aynı oturumda en fazla **4 kez** seri artırabilir;
gerisi sorulur ama seriye sayılmaz.

**Yanlış cevapta seri.** Varsayılan olarak seri **5 azalır** (`minus5`).
Ayarlardan "yarıya düşer" veya "tamamen sıfırlanır" moduna geçebilirsin.
Ölçüm sonucu: %85 hatırlama oranında bir kelimenin 20-seriyi tamamlaması
tam sıfırlamayla ~54 oturum, `minus5` ile ~24 oturum sürüyor.

**Seviye tahmini.** Uydurma değil — Oxford'un kendi CEFR etiketlerinden
hesaplanır. Bir seviye, o seviyedeki kelimelerin %85'ine hakim olununca
tamamlanmış sayılır.

### Ters yön (TR → EN)

Aynı destenin öbür yüzü: Türkçe anlamı görürsün, **İngilizcesini** yazarsın.
Çalışma ekranındaki **↔ Yön** düğmesiyle (veya Ayarlar → Çalışma yönü)
anında çevrilir. Tanıma ile üretim aynı beceri değildir; o yüzden:

- **İlerleme tektir.** Kelime hangi yönde bilinirse bilinsin aynı seri
  ilerler, üst bar aynı sayaçları gösterir; yön yalnızca sorunun biçimini
  değiştirir. (Bir ara yönler ayrı `progress_rev` tablosunda tutuluyordu;
  eski dosyadaki o ilerleme açılışta bir kez ana tabloya katılır.)
- **Kardeş kelimeler kabul edilir.** 2.977 kelimenin 844'ü Türkçe ana anlamını
  başka bir kelimeyle paylaşır (büyük = big / large / great / grand /
  massive). Bunlardan herhangi birini yazarsan doğru sayılır ve kartın kendi
  kelimesi gösterilir. Aynı Türkçe anlamı paylaşmayanlar kabul edilmez
  ("satın almak" için `get` yanlış).
- Ekrandaki ek anlamlar (`büyük · iri · geniş`) soruyu netleştirir.
- Ses düğmesi cevaptan önce gizlidir (telaffuz kelimeyi ele verir); doğru
  cevaptan sonra kelime seslendirilir.
- İngilizce cevapta Türkçe ek soyma yoktur (`car` ≠ `care`). Tolerans:
  büyük/küçük harf, kesme işareti, baştaki `to`/`a`/`the`, 1 harflik yazım
  hatası (uyarılı). Amerikan ve İngiliz yazımının ikisi de geçer.
- Merdiven, aktif pencere, yazarak pekiştir, teyit ve `Ctrl+K` aynen çalışır;
  `Ctrl+K` kabulleri yönle etiketlenir ve `overrides.json`'a **aktarılmaz**
  (o dosya Türkçe kabul listesidir).

**Karışık mod.** Üçüncü seçenek: her kart kendi yönünde gelir, tur yarı yarıya
bölünür (TR → EN havuzu küçükse EN → TR doldurur). Kartın üstündeki rozet
yönü gösterir (`A1 · başlangıç · TR → EN`), soru satırı da değişir
("Türkçe karşılığı?" / "İngilizcesi?"). Aynı kelime bir turda iki yönde
çıkmaz — cevabı ele verirdi. Her kart kendi tablosuna işlenir; kayıtlar
(`reviews.direction`) yönle etiketlenir.

### Örnek cümlelerin Türkçesi

Kartın altındaki İngilizce örnek cümlenin hemen altında Türkçesi de durur;
"Kelimeler" ekranındaki detay panelinde de. 2.637 örnek cümle için
**Google Translate** ile üretildi (`tools/translate_examples.py` →
`tools/examples_tr.json`). Kelime karşılıklarında olduğu gibi bağımsız bir
kaynak yok; A1-B2 düzeyi kısa cümlelerde kalite iyi, ama eş sesli
kelimelerde yanlış anlam seçilebilir (`The lake was still` → "hâlâ" yerine
"durgun" olmalı). Yanlış gördüğün çeviriyi `examples_tr.json`'da elle düzelt,
`py tools/build_dataset.py` ile veri setine işle; script mevcut kayıtların
üstüne yazmaz.

## Cevap değerlendirme

**Katı mod:** yalnızca kelimenin ana anlamı ve yakın eş anlamlıları doğru
sayılır. Sözlüğün uzak anlamları (`alternatives`) kabul edilmez, sadece bilgi
olarak gösterilir.

Yazım toleransı anlamı değil, klavyeyi affeder:

| Girdi | Sonuç |
|---|---|
| `terk et` → `terk etmek` | ✅ mastar eki toleransı |
| `yarısı` → `yarı` | ✅ Türkçe çekim ekleri (iyelik, hâl, çoğul) |
| `kitabı` → `kitap` | ✅ ünsüz yumuşaması geri alınır |
| `ismi` → `isim` | ✅ ünlü düşmesi telafi edilir |
| `sarki` → `şarkı` | ✅ Türkçe karakter serbestliği |
| `birakmak` → `bırakmak` | ✅ |
| `telafuz etmek` → `telaffuz etmek` | ⚠️ doğru sayılır, uyarı gösterilir |
| `onbeş` → `on beş` | ✅ boşluk farkı anlam farkı değildir |
| `60` (sixty) | ✅ sayı kelimelerinde rakam da geçerli |
| `boşlamak` (abandon) | 🔸 uzak anlam — **cezasız**, tekrar denersin |

Her iki tolerans da Ayarlar'dan kapatılabilir.

## "BİLİYORDUM" tuşu (Ctrl+K)

Program bir cevabını haksız yere reddettiğinde alt bardaki yeşil
**✓ BİLİYORDUM, doğru say** butonuna bas (veya `Ctrl+K`). O anda:

- kelime **doğrudan BİLİNENLER listesine** taşınır — tekrar döngüsüne girmez,
  bir daha sorulmaz,
- yazdığın cevap o kelime için **kalıcı olarak kabul edilir**,
- az önceki **ceza geri alınır** (seri, durum, yanlış sayacı eski hâline döner),
- kayıt ilerleme veritabanına düşer, yedeklere de girer.

Bu tuşla taşıdığın kelimeleri iki yerden görebilirsin:

- **Kelimeler → Durum: "Elle onayladıklarım"** — hepsinin listesi. Bir kelimeyi
  seçince detay panelinde `★ Senin onayladıkların: ...` satırı çıkar.
- **Ayarlar → Doğru saydıklarım** — cevap bazında liste; birini geri alabilirsin.

Toplu düzeltme için:

```bash
py tools/apply_flags.py      # işaretleri tools/overrides.json'a işler
py tools/build_dataset.py    # veri setini yeniden üretir
```

Aynı işi Ayarlar'daki **"Veri setine kalıcı işle"** butonu da yapar. Böylece
düzeltmelerin veri seti yeniden üretildiğinde de kalıcı olur.

**Uzak anlam cezalandırılmaz.** Sözlükte var ama ana anlam olmayan bir karşılık
yazarsan program "doğru yoldasın, ama ana anlamını istiyorum" der; hiçbir kayıt
tutulmaz, serin düşmez, aynı kelimeyi tekrar denersin. Kelimeyi bildiğin belli
olduğu için bunu yanlış saymak adil olmaz.

## Dilbilgisi kelimeleri

`would`, `will`, `shall`, `the`, `of` gibi kelimelerin tek başına Türkçe
karşılığı yoktur — "would = -ecekti" ezberlenecek bir şey değil. Bu tür **36
kelime** için karta, cevaptan sonra mavi renkte bir **Türkçe açıklama** satırı
eklenir:

> **would** = -ecekti · -acaktı · -erdi · -ardı
> ℹ will'in geçmiş/şart hâli: "I would go" = Giderdim. · Kibar istek:
> "Would you help?" = Yardım eder misin?
> 💬 He said he would go if he could.

Açıklamalar `tools/notes.json` içinde; istediğini düzenleyip
`py tools/build_dataset.py` ile yeniden üretebilirsin. Aynı açıklama Kelimeler
ekranındaki detay panelinde de görünür.

## Klavye

| Tuş | İşlev |
|---|---|
| `Enter` | Cevapla / sonraki karta geç |
| `Esc` | Bilmiyorum |
| `Ctrl+K` | Biliyordum — kelimeyi bilinenlere taşı |
| `↔ Yön` düğmesi | EN → TR / TR → EN arasında geçiş (ilerleme ayrı) |
| `F11` | Tam ekran aç/kapat |
| `Ctrl+Q` | Çıkış |

Program açılışta ekranı kaplar (maksimize). `F11` başlık çubuğunu da gizleyen
gerçek tam ekrana geçirir.

## Veri seti

`data/oxford3000.json` — **2.977 kelime**. Dört bağımsız kaynağın **konsensüs
puanlamasıyla** birleştirilmesiyle üretildi:

| Kaynak | Katkısı | Kapsam |
|---|---|---|
| [Oxford 3000 PDF](https://www.oxfordlearnersdictionaries.com/external/pdf/wordlists/oxford-3000-5000/The_Oxford_3000.pdf) | resmî kelime listesi + tür + CEFR | referans |
| [firatkaya1/dictionary](https://github.com/firatkaya1/dictionary) | 1.46M kayıtlık EN-TR sözlük, "Common Usage" katmanı | %98.8 |
| [ciwga/Oxford3000_Vocab](https://github.com/ciwga/Oxford3000_Vocab) (MIT) | TR karşılık, İngilizce tanım, örnek cümle, eş/zıt anlam | %88.6 |
| [CagriAldemir gist](https://gist.github.com/CagriAldemir/b5313cc134c07dc9c41951999252231b) | bağımsız üçüncü TR görüş | %91.9 |

Bir Türkçe karşılığın puanı, kaç bağımsız kaynağın onu doğruladığına göre
belirlenir. Bu, tek kaynakta görülen sıralama hatalarını düzeltir
(`book` → tek kaynakta "ayırtmak", konsensüsle **"kitap"**).

Düşük mutabakatlı kelimeler elle gözden geçirilip `tools/overrides.json`
içinde düzeltildi (`album` → "plak" değil **"albüm"**, `being` → "yapı" değil
**"varlık"** gibi ~100 düzeltme). Bir çeviriyi yanlış bulursan bu dosyaya
ekleyip veri setini yeniden üret:

```bash
py tools/build_dataset.py
```

İlerlemen kaybolmaz — eşleşme kelimenin kendisi üzerinden yapılır.

### Neden 3000 değil de 2.977?

"Oxford 3000" yuvarlatılmış bir isim, kesin bir sayı değil. Resmî PDF'de **2.996
giriş** var ve bunların **21'i aynı kelimenin iki ayrı anlamı** olarak ikişer kez
listeleniyor:

| PDF'de iki satır | Bizde tek kart |
|---|---|
| `bank (money)` + `bank (river)` | **bank** = banka, kıyı |
| `bear (animal)` + `bear (deal with)` | **bear** = ayı, katlanmak |
| `close1` + `close2` | **close** = kapatmak, yakın |
| `may` + `May` | **may** = -ebilir, mayıs |

Program kelime başına tek kart gösterdiği için bunlar birleşiyor: 2.996 − 21 =
2.975, artı satırı kayan iki giriş = **2.977 benzersiz kelime**. Hiçbir kelime
atlanmıyor; bu 21 kelimenin **her iki anlamı da** kabul ediliyor
(`close` için hem "kapatmak" hem "yakın" doğru sayılır).

## İngiliz / Amerikan İngilizcesi

Oxford 3000 **İngiliz İngilizcesi** yazımını kullanır: `mum`, `colour`, `centre`,
`favourite`, `theatre`, `neighbour`, `grey`, `maths`, `metre`, `tyre`… 27 kelime
böyle ve Amerikan karşılıkları listede **hiç yok**. Türkiye'de Amerikan
İngilizcesi öğretildiği için bunlar yanlış yazılmış gibi görünür.

Program **varsayılan olarak Amerikan yazımını gösterir** — kartta `mom` yazar,
örnek cümle de birlikte dönüşür (*Mom is cooking dinner.*), İngiliz yazımı ise
cevaptan sonra not olarak görünür. Ayarlar → *İngilizce yazım biçimi* ile
Oxford'un aslına (İngiliz yazımı) geçebilirsin.

Not: `biscuit`, `lift`, `queue`, `rubbish`, `lorry` gibi **kelime** farkları
değiştirilmez — bunlar gerçek İngilizce kelimelerdir, çevirileri doğrudur ve
çoğunun Amerikan eşdeğeri (`cookie`, `truck`…) zaten listede ayrıca vardır.

## Güncelleme

Program **kendini güncellemez**, ama yeni sürümden haberin olur: açılıştan
birkaç saniye sonra arka planda GitHub'ın açık sürüm listesine tek bir istek
atılır (`app/update.py`). Daha yeni bir sürüm varsa üstte ince bir şerit çıkar:

- **İndirme sayfasını aç** → tarayıcıda Releases sayfası açılır, kurulumu sen
  yaparsın. Üstüne kurmak ilerlemeni silmez (`data/progress.db` yerinde kalır).
- **Şimdilik gizle** → o sürüm bir daha hatırlatılmaz (Ayarlar'dan "Şimdi
  kontrol et" dersen yine gösterilir).

Ayrıntılar:

- Günde en fazla **bir** istek atılır; Ayarlar → *Sürüm ve güncelleme*'den
  tamamen kapatılabilir, kapalıyken hiç istek gitmez.
- İstekte **hiçbir kişisel veri yoktur** — ne ilerleme, ne kimlik, ne
  tanımlayıcı. Yalnızca bir GET ve `Oxford3000/<sürüm>` tarayıcı kimliği.
- İnternet yoksa veya GitHub yanıt vermezse sessizce vazgeçilir; o gün
  "bakıldı" sayılmaz, ertesi açılışta yeniden denenir.
- Ağ isteği arka planda yapılır, Tk ve SQLite'a yalnızca ana iş parçacığından
  dokunulur (sonuç bir kuyruğa bırakılır, arayüz onu yoklar).

Sürüm numarasının tek kaynağı **`app/version.py`**. Yeni sürüm çıkarırken
yalnızca oradaki `VERSION` değiştirilir; `version_info.txt` (exe özellikleri)
ve kurulum paketinin sürümü derleme sırasında oradan üretilir:

```bash
py tools/build_setup.py      # exe + dist/Oxford3000-Kurulum-<sürüm>.exe
py tools/update_test.py      # güncelleme kontrolü testi (ağa çıkmaz)
```

Sonra `dist/` içindeki iki dosyayı GitHub'da `v<sürüm>` etiketli yeni bir
Release'e yükle — kullanıcılar şeridi o zaman görür.

## Görünüm ve yazı netliği

Program **yüksek DPI farkındalıdır** (`app/dpi.py`). Windows ekran
ölçeklendirmen %100'den büyükse (%125, %150…) bu olmadan Windows pencereyi
96 DPI'da çizdirip görüntüyü büyütür — yazılar bulanık görünür. Farkındalık
açıkken Tk gerçek çözünürlükte çizer: punto cinsinden tanımlı yazı tipleri
kendiliğinden büyür (11 punto → %125 ekranda 20 yerine 25 piksel) ve kenarlar
keskin kalır. Piksel cinsinden ölçüler (pencere boyutu, satır sarma, çubuk
yükseklikleri) `theme.px()` ile aynı oranda ölçeklenir.

Ayrıca gövde yazısı 11 → 12, küçük yazı 9 → 10 puntoya çıkarıldı ve soluk
metin rengi daha okunur hale getirildi (koyu temada kontrast 5,5 → 7,7).

## Telaffuz

Google TTS ile indirilir, `data/audio/` altında önbelleğe alınır; aynı kelime
bir daha internet gerektirmez. Ayarlar → "Tüm sesleri şimdi indir" ile 3000
kelimenin tamamı (~24 MB) tek seferde indirilip program tamamen çevrimdışı
hale getirilebilir. mp3 çalmak için harici kütüphane kullanılmaz — Windows'un
kendi winmm/MCI arayüzü üzerinden çalınır.

## Dosya yapısı

```
Oxford3000.exe             çalıştırılabilir program (çift tıkla)
main.py                    kaynak koddan giriş noktası
oxford3000.spec            PyInstaller yapılandırması
version_info.txt           exe sürüm/açıklama bilgileri
assets/
  app.ico                  uygulama logosu (6 boyut: 16→256 px)
  logo.png                 logonun büyük hâli
app/
  paths.py                 .py / .exe fark etmeksizin doğru dosya yolları
  db.py                    SQLite şeması ve veri erişimi
  engine.py                kart seçimi, hibrit ritim, durum geçişleri
  matching.py              Türkçe-duyarlı cevap eşleştirme
  stats.py                 istatistikler ve CEFR seviye tahmini
  tts.py                   Google TTS + önbellek + MCI oynatma
  ui/
    theme.py               renk paleti, tipografi, ttk stilleri
    app_window.py          ana pencere ve üst durum barı
    dashboard.py           ana ekran
    quiz_view.py           kart ekranı
    wordlist_view.py       kelime listeleri ve detay paneli
    stats_view.py          grafikler
    settings_view.py       ayarlar, yedekleme
app/
  backup.py                otomatik yedekleme ve kurtarma
data/
  oxford3000.json          kelime havuzu (üretilmiş)
  progress.db              ilerlemen (otomatik oluşur)
  backups/                 otomatik yedekler (son 20)
  audio/                   telaffuz önbelleği
tools/
  build_dataset.py         kaynakları birleştirip veri setini üretir
  overrides.json           elle yapılmış çeviri düzeltmeleri
  notes.json               dilbilgisi kelimeleri için Türkçe açıklamalar
  apply_flags.py           işaretlenen cevapları overrides.json'a işler
  build_exe.py             exe + ikon + kısayol üretir
  make_icon.py             uygulama logosunu çizer
  simulate.py              motoru sahte kullanıcıyla test eder
  smoke.py                 tüm ekranları açıp kontrol eder
```

## Yedekleme ve kurtarma

İlerlemen `data/progress.db` içinde tutulur ve **otomatik yedeklenir**:

- Program her **açılışta** ve her **kapanışta** yedek alır (`data/backups/`)
- Son **20** yedek saklanır, eskiler kendiliğinden silinir
- Açılışta ilerleme dosyası **yoksa veya bozuksa**, en yeni sağlam yedekten
  kendiliğinden geri yüklenir ve sana haber verilir
- Boş veritabanı yedeklenmez (çalışılmamış hâl iyi yedeğin üzerine yazmasın)

Ayarlar → **Otomatik yedekler** bölümünde tüm yedekleri tarih ve kelime sayısıyla
görebilir, birine geri dönebilir, elle yedek alabilir veya klasörü açabilirsin.

Ayrıca Ayarlar → *Görünüm ve veri* → **Başka yere kopyala** ile yedeği harici bir
diske alabilirsin.

**Test araçları gerçek ilerlemene dokunamaz.** `tools/` altındaki testler
`tools/_guard.py` üzerinden kendi veritabanlarını alır; biri yanlışlıkla
`data/progress.db` istemeye kalkarsa program çalışmayı reddeder.

    py tools/backup_test.py     # yedekleme/kurtarma testi
