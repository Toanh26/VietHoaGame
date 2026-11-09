//=============================================================================
// VietTranslate.js  —  Việt hoá RPG Maker MV / MZ lúc chạy game
//=============================================================================
/*:
 * @target MV MZ
 * @plugindesc Việt hoá: font tiếng Việt + từ điển dịch lúc chạy (runtime). v1.0
 * @author vntrans
 *
 * @param DictionaryFile
 * @text File từ điển (trong data/)
 * @desc Tạo bằng: vntrans export-dict -o vi_dictionary.json. Để trống nếu không dùng.
 * @default vi_dictionary.json
 *
 * @param FontFile
 * @text File font (trong fonts/)
 * @desc Font hỗ trợ đủ dấu tiếng Việt, vd. BeVietnamPro-Regular.ttf. Để trống = giữ font gốc.
 * @default
 *
 * @param FontSize
 * @text Cỡ chữ
 * @desc 0 = giữ nguyên cỡ chữ của game.
 * @type number
 * @default 0
 *
 * @param TranslateDrawText
 * @text Dịch cả chữ vẽ trực tiếp
 * @desc Dịch chữ do plugin khác vẽ bằng Bitmap.drawText (khớp nguyên câu).
 * @type boolean
 * @default true
 *
 * @param AutoWrap
 * @text Tự xuống dòng
 * @desc Tự ngắt dòng hội thoại quá dài theo độ rộng khung thoại.
 * @type boolean
 * @default true
 *
 * @help
 * Plugin này làm 2 việc:
 *  1. Thay font của game bằng font có dấu tiếng Việt (font gốc của nhiều game
 *     Nhật/Trung không có chữ ạ, ặ, ữ, ...).
 *  2. Dịch lúc chạy: mọi câu đi qua hộp thoại / cửa sổ (convertEscapeCharacters)
 *     hoặc Bitmap.drawText mà khớp với từ điển sẽ được thay bằng bản dịch.
 *     Hữu ích cho chữ nằm trong plugin khác mà `vntrans apply` không ghi tới.
 *
 * Cài đặt:
 *  - Chép VietTranslate.js vào js/plugins/, bật trong Plugin Manager
 *    (đặt ở CUỐI danh sách).
 *  - Chép vi_dictionary.json vào data/ và file font vào fonts/.
 */
(function () {
  "use strict";
  var NAME = "VietTranslate";
  var P = PluginManager.parameters(NAME);
  var DICT_FILE = String(P.DictionaryFile || "").trim();
  var FONT_FILE = String(P.FontFile || "").trim();
  var FONT_SIZE = Number(P.FontSize || 0);
  var DRAW_TEXT = String(P.TranslateDrawText || "true") === "true";
  var AUTO_WRAP = String(P.AutoWrap || "true") === "true";
  var FONT_NAME = "VietTranslateFont";
  var IS_MZ = Utils.RPGMAKER_NAME === "MZ";

  // ---------------------------------------------------------------- từ điển
  window.$viDictionary = null;
  if (DICT_FILE) {
    DataManager._databaseFiles.push({ name: "$viDictionary", src: DICT_FILE });
  }

  function lookup(text) {
    var d = window.$viDictionary;
    if (!d || typeof text !== "string" || !text) return text;
    if (Object.prototype.hasOwnProperty.call(d, text)) return d[text];
    if (text.indexOf("\n") >= 0) {
      // thử dịch từng dòng
      var changed = false;
      var lines = text.split("\n").map(function (ln) {
        if (Object.prototype.hasOwnProperty.call(d, ln)) { changed = true; return d[ln]; }
        return ln;
      });
      if (changed) return lines.join("\n");
    }
    return text;
  }
  window.VietTranslate = { lookup: lookup };

  var _convert = Window_Base.prototype.convertEscapeCharacters;
  Window_Base.prototype.convertEscapeCharacters = function (text) {
    return _convert.call(this, lookup(text));
  };

  if (DRAW_TEXT) {
    var _drawText = Bitmap.prototype.drawText;
    Bitmap.prototype.drawText = function (text, x, y, maxWidth, lineHeight, align) {
      if (typeof text === "string") text = lookup(text);
      return _drawText.call(this, text, x, y, maxWidth, lineHeight, align);
    };
  }

  // ---------------------------------------------------------------- tự xuống dòng
  function measure(win, s) {
    s = s.replace(/\x1bI\[\d+\]/gi, "WW").replace(/\x1b[A-Z]+\[[^\]]*\]/gi, "").replace(/\x1b./g, "");
    return win.textWidth(s);
  }
  function wrapText(win, text) {
    if (!win.contents || typeof text !== "string") return text;
    win.resetFontSettings();
    var maxW = win.contents.width - (win.newLineX({ rtl: false, text: text }) || 0) - 8;
    if (maxW < 100) return text;
    var out = [];
    text.split("\n").forEach(function (line) {
      if (measure(win, line) <= maxW) { out.push(line); return; }
      var cur = "";
      line.split(" ").forEach(function (w) {
        var cand = cur ? cur + " " + w : w;
        if (cur && measure(win, cand) > maxW) { out.push(cur); cur = w; } else { cur = cand; }
      });
      out.push(cur);
    });
    return out.join("\n");
  }
  if (AUTO_WRAP) {
    var _wmConvert = Window_Message.prototype.convertEscapeCharacters;
    Window_Message.prototype.convertEscapeCharacters = function (text) {
      return wrapText(this, _wmConvert.call(this, text));
    };
  }

  // ---------------------------------------------------------------- font
  if (FONT_FILE) {
    if (IS_MZ) {
      var _loadFonts = Scene_Boot.prototype.loadGameFonts;
      Scene_Boot.prototype.loadGameFonts = function () {
        _loadFonts.call(this);
        FontManager.load(FONT_NAME, FONT_FILE);
      };
      var _mainFace = Game_System.prototype.mainFontFace;
      Game_System.prototype.mainFontFace = function () {
        return FONT_NAME + ", " + _mainFace.call(this);
      };
      if (FONT_SIZE > 0) {
        Game_System.prototype.mainFontSize = function () { return FONT_SIZE; };
      }
    } else {
      var _bootCreate = Scene_Boot.prototype.create;
      Scene_Boot.prototype.create = function () {
        _bootCreate.call(this);
        Graphics.loadFont(FONT_NAME, "fonts/" + FONT_FILE);
      };
      var _bootReady = Scene_Boot.prototype.isReady;
      Scene_Boot.prototype.isReady = function () {
        // chờ font tối đa 5 giây; font lỗi thì chạy tiếp bằng font gốc, không treo game
        if (!this._vnFontWait) this._vnFontWait = Date.now();
        var fontOk = Graphics.isFontLoaded(FONT_NAME) || Date.now() - this._vnFontWait > 5000;
        return _bootReady.call(this) && fontOk;
      };
      var _stdFace = Window_Base.prototype.standardFontFace;
      Window_Base.prototype.standardFontFace = function () {
        return FONT_NAME + ", " + _stdFace.call(this);
      };
      if (FONT_SIZE > 0) {
        Window_Base.prototype.standardFontSize = function () { return FONT_SIZE; };
      }
    }
  }
})();
