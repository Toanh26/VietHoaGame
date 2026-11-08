import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_roundtrip import make_game  # noqa: E402

from vntrans.auto.detect import detect  # noqa: E402
from vntrans.auto.jobs import make_job  # noqa: E402
from vntrans.auto.unity import LiveServer, set_ini  # noqa: E402
from vntrans.translators import DummyTranslator  # noqa: E402


class AutoJobs(unittest.TestCase):
    def test_rpgmaker_job_and_restore(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            make_game(t)
            g = t / "rpg"
            (g / "Game.exe").write_bytes(b"MZ")
            (g / "www" / "js").mkdir(parents=True)
            (g / "www" / "js" / "plugins.js").write_text('// x\nvar $plugins =\n[\n{"name":"Other","status":true,"description":"","parameters":{}}\n];\n')
            orig = (g / "www/data/Map001.json").read_text()
            info = detect(g)
            self.assertEqual(info.engine, "rpgmaker_mv")
            asked = []
            job = make_job(info, DummyTranslator(), log=lambda m: None, confirm=lambda n, c: asked.append(n) or True)
            self.assertTrue(job.run())
            self.assertTrue(asked and asked[0] > 5)
            m = json.loads((g / "www/data/Map001.json").read_text())
            self.assertTrue(m["events"][1]["pages"][0]["list"][1]["parameters"][0].startswith("[VI]"))
            plugins = (g / "www/js/plugins.js").read_text()
            self.assertIn('"Other"', plugins)
            self.assertIn('"VietTranslate"', plugins)
            self.assertTrue((g / "www/js/plugins/VietTranslate.js").exists())
            self.assertTrue((g / "www/data/vi_dictionary.json").exists())
            # chạy lần 2: không dịch lại, không chồng [VI] [VI]
            asked.clear()
            make_job(detect(g), DummyTranslator(), log=lambda m: None, confirm=lambda n, c: asked.append(n) or True).run()
            self.assertEqual(asked, [])
            m = json.loads((g / "www/data/Map001.json").read_text())
            self.assertNotIn("[VI] [VI]", json.dumps(m))
            make_job(detect(g), None, log=lambda m: None).restore()
            self.assertEqual((g / "www/data/Map001.json").read_text(), orig)
            self.assertNotIn("VietTranslate", (g / "www/js/plugins.js").read_text())

    @unittest.skipIf(os.name == "nt", "dùng shell script giả làm game")
    def test_renpy_job_with_fake_game(self):
        with tempfile.TemporaryDirectory() as t:
            g = Path(t) / "rp"
            (g / "game").mkdir(parents=True)
            (g / "renpy").mkdir()
            (g / "MyVN.py").write_text("")
            exe = g / "MyVN.exe"
            # "game" giả: đọc flag, ghi kết quả quét như zz_vntrans.rpy
            exe.write_text('#!/bin/sh\nout=$(cat game/vntrans_scan.flag)\n'
                           'printf \'[{"t":"Hello [mc]!","who":"e","f":"game/script.rpy","l":3,"k":"say"},'
                           '{"t":"Go left","f":"game/script.rpy","l":5,"k":"menu"}]\' > "$out"\n')
            exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
            (g / "game" / "vntrans_missing.txt").write_text('"Start"\n"Load"\n')
            info = detect(g)
            self.assertEqual(info.engine, "renpy")
            self.assertEqual(info.exe.name, "MyVN.exe")
            make_job(info, DummyTranslator(), log=lambda m: None).run()
            d = json.loads((g / "game" / "vntrans_vi.json").read_text())
            self.assertEqual(d["Hello [mc]!"], "[VI] Hello [mc]!")
            self.assertEqual(d["Start"], "[VI] Start")
            self.assertTrue((g / "game" / "zz_vntrans.rpy").exists())
            self.assertFalse((g / "game" / "vntrans_scan.flag").exists())
            make_job(info, None, log=lambda m: None).restore()
            self.assertFalse((g / "game" / "zz_vntrans.rpy").exists())

    def test_unity_config_and_live_server(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            ini = t / "a.ini"
            ini.write_text("[Service]\nEndpoint=GoogleTranslate\nFallbackEndpoint=x\n\n[General]\nLanguage=en\n")
            set_ini(ini, {"Service": {"Endpoint": "CustomTranslate"}, "General": {"Language": "vi"},
                          "Custom": {"Url": "http://127.0.0.1:1/translate"}})
            s = ini.read_text()
            self.assertIn("Endpoint=CustomTranslate", s)
            self.assertIn("FallbackEndpoint=x", s)
            self.assertIn("Language=vi", s)
            self.assertIn("[Custom]\nUrl=http://127.0.0.1:1/translate", s)

            srv = LiveServer(DummyTranslator(), t / "cache.json", log=lambda m: None, port=47299)
            srv.start()
            try:
                res = {}

                def ask(txt):
                    u = "http://127.0.0.1:47299/translate?" + urllib.parse.urlencode({"from": "en", "to": "vi", "text": txt})
                    res[txt] = urllib.request.urlopen(u, timeout=20).read().decode("utf-8")

                th = [threading.Thread(target=ask, args=(x,)) for x in ("New Game", "<b>Options</b>", "Quit")]
                [x.start() for x in th]
                [x.join() for x in th]
                self.assertEqual(res["New Game"], "[VI] New Game")
                self.assertEqual(res["<b>Options</b>"], "[VI] <b>Options</b>")
                self.assertIn("Quit", json.loads((t / "cache.json").read_text()))
            finally:
                srv.stop()

    def test_unity_detect(self):
        with tempfile.TemporaryDirectory() as t:
            g = Path(t)
            (g / "Cool_Data" / "Managed").mkdir(parents=True)
            (g / "Cool_Data" / "Managed" / "Assembly-CSharp.dll").write_bytes(b"")
            (g / "Cool.exe").write_bytes(b"MZ")
            self.assertEqual(detect(g).engine, "unity_mono")
            (g / "Cool_Data" / "Managed" / "Assembly-CSharp.dll").unlink()
            (g / "GameAssembly.dll").write_bytes(b"")
            self.assertEqual(detect(g).engine, "unity_il2cpp")


if __name__ == "__main__":
    unittest.main()
