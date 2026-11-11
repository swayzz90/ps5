import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_stock import classify_page

TITLE = "<h1>Generalüberholt und Zertifiziert PlayStation®5 Konsole (Modellgruppe - Slim)</h1>"

class StockTests(unittest.TestCase):
    def test_out_of_stock(self):
        result = classify_page(TITLE + "<p>Derzeit nicht vorrätig.</p><button>Nicht zum Kauf erhältlich</button>")
        self.assertEqual(result[0], "unavailable")

    def test_available(self):
        result = classify_page(TITLE + "<button>In den Einkaufswagen</button>")
        self.assertEqual(result[0], "available")

    def test_conflicting_signals(self):
        result = classify_page(TITLE + "<p>Derzeit nicht vorrätig.</p><button>In den Einkaufswagen</button>")
        self.assertEqual(result[0], "unknown")

    def test_captcha_does_not_look_like_availability(self):
        result = classify_page("<h1>Captcha</h1><button>In den Einkaufswagen</button>")
        self.assertEqual(result[0], "unknown")

    def test_void_elements_in_navigation_do_not_hide_product(self):
        result = classify_page("<nav><img src=\"x\"><input><p>Menu</p></nav>" + TITLE + "<button>In den Einkaufswagen</button>")
        self.assertEqual(result[0], "available")

    def test_scripts_not_considered_visible(self):
        result = classify_page(TITLE + "<script>const x = 'In den Einkaufswagen'</script><p>Nicht zum Kauf erhältlich</p>")
        self.assertEqual(result[0], "unavailable")

if __name__ == "__main__": unittest.main()
