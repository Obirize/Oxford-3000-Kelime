"""Oxford 3000 - Ingilizce Kelime Ezberleme

Calistirma:
    py main.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Yuksek DPI farkindaligi HER SEYDEN once acilmali - ilk pencere olustuktan
# sonra Windows bunu yok sayar ve yazilar bulanik kalir. (app/dpi.py)
from app import dpi  # noqa: E402

dpi.enable()

import tkinter.messagebox as mb  # noqa: E402

from app import backup, db, handoff  # noqa: E402
from app.ui.app_window import AppWindow  # noqa: E402


def main() -> int:
    if not db.WORDS_JSON.exists():
        mb.showerror(
            "Kelime listesi bulunamadi",
            f"{db.WORDS_JSON} yok.\n\nOnce su komutu calistir:\n"
            f"    py tools/build_dataset.py",
        )
        return 1

    # Ilerleme dosyasi silinmis veya bozulmussa en yeni saglam yedekten don.
    recovered = backup.recover_if_needed(db.DB_PATH)
    if recovered:
        mb.showinfo(
            "İlerleme kurtarıldı",
            "İlerleme dosyası bulunamadı veya bozuktu.\n\n"
            f"Şu yedekten geri yüklendi:\n{backup.describe(recovered)}",
        )

    # Burada ilerleme yoksa baska bir kopyada (orn. tasinabilir exe'nin yaninda
    # ya da eski kurulum klasorunde) duruyor olabilir. Sorup devralalim -
    # yoksa kullanici "ilerlemem gitti" sanir. (app/handoff.py)
    if handoff.is_empty(db.DB_PATH):
        other = handoff.find_elsewhere(db.DB_PATH)
        if other and mb.askyesno(
            "İlerlemeni buraya taşıyalım mı?",
            "Bu klasörde kayıtlı ilerleme yok, ama başka bir klasörde "
            "çalışılmış bir ilerleme bulundu:\n\n"
            f"{other.label}\n\n"
            "Buraya kopyalansın mı?\n"
            "(Eski dosyaya dokunulmaz, yerinde kalır.)",
        ):
            if handoff.adopt(other, db.DB_PATH):
                mb.showinfo("Taşındı", "İlerlemen bu kuruluma kopyalandı.")
            else:
                mb.showerror(
                    "Taşınamadı",
                    "İlerleme kopyalanamadı. Ayarlar → 'Dosyadan geri yükle' "
                    f"ile şu dosyayı seçebilirsin:\n{other.path}",
                )

    # Her acilista yedek al (bos veritabani yedeklenmez).
    backup.create(db.DB_PATH)

    conn = db.connect()
    db.sync_words(conn)
    AppWindow(conn).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
