"""Oxford 3000 - Ingilizce Kelime Ezberleme

Calistirma:
    py main.py
"""

import sys
import tkinter.messagebox as mb
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import backup, db
from app.ui.app_window import AppWindow


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

    # Her acilista yedek al (bos veritabani yedeklenmez).
    backup.create(db.DB_PATH)

    conn = db.connect()
    db.sync_words(conn)
    AppWindow(conn).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
