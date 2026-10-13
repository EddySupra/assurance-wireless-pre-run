var background = (function () {
  let tmp = {};
  chrome.runtime.onMessage.addListener(function (request) {
    for (let id in tmp) {
      if (tmp[id] && (typeof tmp[id] === "function")) {
        if (request.path === "background-to-options") {
          if (request.method === id) {
            tmp[id](request.data);
          }
        }
      }
    }
  });
  /*  */
  return {
    "receive": function (id, callback) {
      tmp[id] = callback;
    },
    "send": function (id, data) {
      chrome.runtime.sendMessage({
        "method": id, 
        "data": data,
        "path": "options-to-background"
      }, function () {
        return chrome.runtime.lastError;
      });
    }
  }
})();

var config = {
  "elements": {},
  "style": {
    "textarea": {
      "tabSize": 2,
      "fence": false,
      "softTabs": true,
      "autoOpen": true,
      "overwrite": true,
      "autoStrip": true,
      "autoIndent": true,
      "replaceTab": true
    }
  },
  "hostname": function (url) {
    try {
      url = url.replace("www.", '');
      let s = url.indexOf("//") + 2;
      if (s > 1) {
        let o = url.indexOf('/', s);
        if (o > 0) {
          return url.substring(s, o);
        } else {
          o = url.indexOf('?', s);
          if (o > 0) {
            return url.substring(s, o);
          } else {
            return url.substring(s);
          }
        }
      } else {
        return url;
      }
    } catch (e) {
      return url;
    }
  },
  "interface": {
    "timeout": null,
    "render": function (changes) {
      const length = changes ? Object.keys(changes).length : 0;
      const inputs = [
        ...document.querySelectorAll("input[type='radio']"),
        ...document.querySelectorAll("input[type='number']"),
        ...document.querySelectorAll("input[type='checkbox']")
      ];
      /*  */
      chrome.storage.local.get(null, function (e) {
        if (length !== 1) {
          const details = [...document.querySelectorAll("details")];
          /*  */
          for (let i = 0; i < details.length; i++) {
            details[i].open = e["section-" + (i + 1)];
          }
          /*  */
          config.elements.support.checked = e.opensupport;
          config.elements.toggleaction.checked = e.toggleaction;
          config.elements.documentroot.checked = e.documentroot;
          config.elements.nativeinline.checked = e.nativeinline;
          config.elements.nativeignore.checked = e.nativeignore;
          config.elements.nativerecheck.checked = e.nativerecheck;
          config.elements.nativerespect.checked = e.nativerespect;
          config.elements.nativecontinue.checked = e.nativecontinue;
          config.elements.nativepriority.checked = e.nativepriority;
          config.elements.nativesupports.checked = e.nativesupports;
          config.elements.nativedeeprules.checked = e.nativedeeprules;
          config.elements.nativekeyframes.checked = e.nativekeyframes;
          config.elements.checkstylesheet.checked = e.checkstylesheet;
          config.elements.nativeforcefont.checked = e.nativeforcefont;
          config.elements.nativeclassname.checked = e.nativeclassname;
          config.elements.mapcssvariables.checked = e.mapcssvariables;
          config.elements.inclusiveaction.checked = e.inclusiveaction;
          config.elements.temporarily.delay.value = e.temporarilydelay;
          config.elements.nativemediaquery.checked = e.nativemediaquery;
          config.elements.nativecompatible.checked = e.nativecompatible;
          config.elements.nativeremoveimage.checked = e.nativeremoveimage;
          config.elements.nativeremovecolor.checked = e.nativeremovecolor;
          config.elements.nativedarkenimage.checked = e.nativedarkenimage;
          config.elements.nativeforceborder.checked = e.nativeforceborder;
          config.elements.temporarily.action.checked = e.temporarilyaction;
          config.elements.nativerangelimitmin.value = e.nativerangelimitmin;
          config.elements.nativeforcesvgfill.checked = e.nativeforcesvgfill;
          config.elements.nativebestpageload.checked = e.nativebestpageload;
          config.elements.nativerangelimitmax.value = e.nativerangelimitmax;
          config.elements.temporarily.display.checked = e.temporarilydisplay;
          config.elements.nativecssstylesheet.checked = e.nativecssstylesheet;
          config.elements.nativerechecktimeout.value = e.nativerechecktimeout;
          config.elements.temporarily.threshold.value = e.temporarilythreshold;
          config.elements.nativeforceboxshadow.checked = e.nativeforceboxshadow;
          config.elements.nativedarkenvariable.checked = e.nativedarkenvariable;
          config.elements.nativeforcesvgstroke.checked = e.nativeforcesvgstroke;
          config.elements.nativebackgroundblend.checked = e.nativebackgroundblend;
          config.elements.nativeforcetextshadow.checked = e.nativeforcetextshadow;
          config.elements.nativeforcebackground.checked = e.nativeforcebackground;
          config.elements.nativebestperformance.checked = e.nativebestperformance;
          config.elements.temporarily.brightness.checked = e.temporarilybrightness;
          config.elements.temporarily.simpledark.checked = e.temporarilysimpledark;
          config.elements.nativeforceborderwidth.checked = e.nativeforceborderwidth;
          config.elements.nativerangethresholdmin.value = e.nativerangethresholdmin;
          config.elements.nativerangethresholdmax.value = e.nativerangethresholdmax;
          config.elements.nativeforceclosetowhite.checked = e.nativeforceclosetowhite;
          config.elements.nativebackgroundrelated.checked = e.nativebackgroundrelated;
          config.elements.nativebackgroundinitial.checked = e.nativebackgroundinitial;
          config.elements.nativeforcetransparency.checked = e.nativeforcetransparency;
          config.elements.nativebackgroundfallback.checked = e.nativebackgroundfallback;
          config.elements.nativeforceclosetowhitemin.value = e.nativeforceclosetowhitemin;
          config.elements.nativeforceclosetowhitemax.value = e.nativeforceclosetowhitemax;
          config.elements.nativebackgroundtransparency.value = e.nativebackgroundtransparency;
          config.elements.nativeforceclosetowhitepercent.value = e.nativeforceclosetowhitepercent;
          /*  */
          config.elements.nativeperformanceobserver.checked = e.nativeperformanceobserver;
          config.elements.nativeforcebackgroundcolor.checked = e.nativeforcebackgroundcolor;
          /*  */
          config.elements.nativedarkengradient.darkshade.value = e.nativedarkenshade;
          config.elements.nativedarkengradient.action.checked = e.nativedarkengradient;
          /*  */
          config.elements.scheduleon.value = e.scheduleon;
          config.elements.scheduleoff.value = e.scheduleoff;
          config.elements.scheduleaction.checked = e.scheduleaction;
          /*  */
          config.elements.excludeiframes.checked = e.excludeiframes;
          config.elements.excludecsscolorscheme.checked = e.excludecsscolorscheme;
          config.elements.excludedarkbackground.checked = e.excludedarkbackground;
          config.elements.excludemetacolorscheme.checked = e.excludemetacolorscheme;
          config.elements.excludeincolorschemedark.checked = e.excludeincolorschemedark;
          config.elements.excludedarkbackgroundnative.checked = e.excludedarkbackgroundnative;
          config.elements.excludedarkbackgroundthreshold.value = e.excludedarkbackgroundthreshold;
          /*  */
          config.elements.nativecolorful.action.checked = e.nativecolorful;
          config.elements.nativecolorful.svg.checked = e["nativecolorful-svg"];
          config.elements.nativecolorful.font.checked = e["nativecolorful-font"];
          config.elements.nativecolorful.border.checked = e["nativecolorful-border"];
          config.elements.nativecolorful.background.checked = e["nativecolorful-background"];
          /*  */
          config.elements.colortemperature.action.checked = e.colortemperature;
          config.elements.colortemperature.red.value = e["colortemperature-red"];
          config.elements.colortemperature.blue.value = e["colortemperature-blue"];
          config.elements.colortemperature.green.value = e["colortemperature-green"];
          config.elements.colortemperature.output.red.value = e["colortemperature-red"];
          config.elements.colortemperature.output.blue.value = e["colortemperature-blue"];
          config.elements.colortemperature.output.green.value = e["colortemperature-green"];
          config.elements.colortemperature.opacity.value = e["colortemperature-opacity"];
          config.elements.colortemperature.whitelist.value = e["colortemperature-whitelist"];
          config.elements.colortemperature.output.opacity.value = e["colortemperature-opacity"] + '%';
          /*  */
          if (config.elements.inclusiveaction.checked) {
            config.elements.toggleaction.closest("label").removeAttribute("disabled");
          } else {
            config.elements.toggleaction.closest("label").setAttribute("disabled", '');
          }
          /*  */
          for (let name in website.custom.regex.rules) {
            let element = document.getElementById(name);
            if (element) element.checked = e[name];
          }
          /*  */
          for (let i = 1; i <= website.total.themes.number; i++) {
            let element = document.getElementById("dark_" + i);
            if (element) element.checked = e["dark_" + i];
          }
        }
        /*  */
        config.elements.fontsize.value = e.fontsize;
        document.documentElement.style.setProperty("--font-size", e.fontsize + "px");
        /*  */
        config.elements.custom.value = e.custom;
        config.elements.nativecssrules.value = e.nativecssrules;
        config.elements.cookie.value = e.cookie ? e.cookie.join(', ') : '';
        config.elements.whitelist.value = e.whitelist ? e.whitelist.join(', ') : '';
        config.elements.temporarily.fieldset.disabled = e.temporarilyaction === false;
        config.elements.nativecolorful.fieldset.disabled = e.nativecolorful === false;
        config.elements.colortemperature.fieldset.disabled = e.colortemperature === false;
        config.elements.inclusivelist.value = e.inclusivelist ? e.inclusivelist.join(', ') : '';
        config.elements.excludeclassnames.value = e.excludeclassnames ? e.excludeclassnames.join(', ') : '';
        config.elements.excludeattributes.value = e.excludeattributes ? e.excludeattributes.join(', ') : '';
        config.elements.nativedarkengradient.fieldset.disabled = e.nativedarkengradient === false && e.nativedarkenvariable === false;
        /*  */
        for (let color in e.nativecssvariables) {
          let element = document.getElementById(color);
          if (element) element.value = e.nativecssvariables[color];
        }
        /*  */
        for (let i = 0; i < inputs.length; i++) {
          const input = inputs[i];
          if (input) {
            const label = input.parentNode;
            const flag = input.checked || input.type === "number";
            const color = {"normal": "rgb(135, 135, 135)", "highlight": "rgb(193, 193, 193)"};
            if (label) {
              label.style.color = flag ? color.highlight : color.normal;
              label.setAttribute("state", flag ? "enabled" : "disabled");
            }
            //
            if (input.dataset) {
              if (input.dataset.native !== undefined) {
                const td = input.closest("td");
                if (td) {
                  const div = td.querySelector("div");
                  if (div) {
                    flag ? div.removeAttribute("disabled") : div.setAttribute("disabled", '');
                  }
                }
              }
            }
          }
        }
      });
    }
  },
  "handle": {
    "reset": function () {
      config.elements.reset.click();
    },
    "mouseleave": function () {
      let footer = document.querySelector(".footer .title");
      if (footer) footer.textContent = '';
    },
    "mouseenter": function (e) {
      let title = e.target.getAttribute("title");
      let footer = document.querySelector(".footer .title");
      /*  */
      if (footer) footer.textContent = title ? title : '';
    },
    "background": function (e) {
      if (e && e.target) {
        if (e.target.id === "reset-addon") {
          const action = window.confirm("Reset the addon to factory settings?\nPlease note that all changes for custom styles, whitelisted items, selected options, etc. will be lost.");
          if (action) background.send(e.target.id);
        } else {
          background.send(e.target.id);
        }
      }
    },
    "toggle": function (e) {
      let close = e.target.id === "close-overlay";
      let closest = e.target.closest(".container");
      let container = document.querySelector(".container");
      /*  */
      if (close || closest !== container) {
        let status = config.elements.overlay.getAttribute("status");
        config.elements.overlay.setAttribute("status", status === "show" ? "hide": "show");
      }
    },
    "click": function () {
      let tmp = {};
      let id = this.id;
      let checked = this.checked;
      /*  */
      if (id.indexOf("dark_") !== -1) {
        for (let i = 1; i <= website.total.themes.number; i++) {
          let element = document.getElementById("dark_" + i);
          if (element) element.checked = false;
        }
        /*  */
        document.getElementById(id).checked = checked;
      }
      /*  */
      for (let name in website.custom.regex.rules) {
        let element = document.getElementById(name);
        if (element) tmp[name] = element.checked;
      }
      /*  */
      for (let i = 1; i <= website.total.themes.number; i++) {
        let element = document.getElementById("dark_" + i);
        if (element) tmp["dark_" + i] = element.checked;
      }
      /*  */
      chrome.storage.local.set(tmp);
    },
    "store": function (e) {
      const id = e.target.id;
      /*  */
      if (id.startsWith("--native-dark-")) {
        const value = e.target.value;
        chrome.storage.local.get("nativecssvariables", function (e) {
          e.nativecssvariables[id] = value;
          chrome.storage.local.set({
            "nativecssvariables": e.nativecssvariables
          });
        });
      } else {
        let tmp = {};
        const cond_0 = id === "nativedarkenshade";
        const cond_1 = id === "nativerangelimitmin" || id === "nativerangelimitmax";
        const cond_2 = id === "temporarilydelay" || id === "temporarilythreshold" || id === "nativerechecktimeout";
        const cond_3 = id === "nativerangethresholdmin" || id === "nativerangethresholdmax" || id === "nativebackgroundtransparency";
        const cond_4 = id === "nativeforceclosetowhitemin" || id === "nativeforceclosetowhitemax" || id === "nativeforceclosetowhitepercent";
        const cond_5 = id === "custom" || id === "fontsize" || id === "nativecssrules" || id === "scheduleon" || id === "scheduleoff" || id === "excludedarkbackgroundthreshold";
        const cond_6 = id === "colortemperature-red" || id === "colortemperature-green" || id === "colortemperature-blue" || id === "colortemperature-opacity" || id === "colortemperature-whitelist";
        /*  */
        tmp[id] = cond_0 || cond_1 || cond_2 || cond_3 || cond_4 || cond_5 || cond_6 ? e.target.value : e.target.checked;
        /*  */
        if (id === "temporarilybrightness" && tmp[id]) {
          tmp["temporarilydisplay"] = false;
          tmp["temporarilysimpledark"] = false;
        }
        /*  */
        if (id === "temporarilydisplay" && tmp[id]) {
          tmp["temporarilybrightness"] = false;
          tmp["temporarilysimpledark"] = false;
        }
        /*  */
        if (id === "temporarilysimpledark" && tmp[id]) {
          tmp["temporarilydisplay"] = false;
          tmp["temporarilybrightness"] = false;
        }
        /*  */
        if (id === "nativeignore" && tmp[id]) {
          tmp["nativerespect"] = false;
          tmp["nativecompatible"] = false;
        }
        /*  */
        if (id === "nativerespect" && tmp[id]) {
          tmp["nativeignore"] = false;
          tmp["nativecompatible"] = false;
        }
        /*  */
        if (id === "nativecompatible" && tmp[id]) {
          tmp["nativeignore"] = false;
          tmp["nativerespect"] = false;
        }
        /*  */
        if (id === "nativebestperformance" && tmp[id]) {
          tmp["nativebestpageload"] = false;
          tmp["nativeperformanceobserver"] = false;
        }
        /*  */
        if (id === "nativebestpageload" && tmp[id]) {
          tmp["nativebestperformance"] = false;
          tmp["nativeperformanceobserver"] = true;
          //
          if (window.PerformanceLongTaskTiming === undefined) {
            window.alert("Your browser does not support this option!");
            //
            config.elements.nativebestperformance.checked = true;
            tmp["nativeperformanceobserver"] = false;
            tmp["nativebestperformance"] = true;
            e.target.checked = false;
            tmp[id] = false;
          }
        }
        /*  */
        if (id === "toggleaction") {
          if (e.target.checked) {
            background.send("toggle-dark");
          }
        }
        /*  */
        if (id === "inclusiveaction") {
          if (e.target.checked) {
            if (config.elements.toggleaction.checked) {
              background.send("toggle-dark");
            }
          }
        }
        /*  */
        if (id === "scheduleaction") {
          chrome.permissions.request({"permissions": ["alarms"]}, function (granted) {
            if (granted) {
              /*  */
            } else {
              config.elements.scheduleaction.checked = false;
              chrome.storage.local.set({"scheduleaction": false});
              window.alert("The 'alarms' permission is required to be able to set schedules.");
            }
          });
        }
        /*  */
        chrome.storage.local.set(tmp);
      }
    }
  },
  "load": function () {
    const test = document.getElementById("test-dark-mode");
    const reset = document.getElementById("reset-dark-mode");
    const summary = [...document.querySelectorAll("summary")];
    const pack = document.getElementById("dark-browsing-pack");
    const donation = document.getElementById("make-a-donation");
    const tutorial = document.getElementById("youtube-tutorial");
    const support = document.getElementById("open-support-page");
    const items = [...document.querySelectorAll("td[id*='-item']")];
    /*  */
    reset.addEventListener("click", config.handle.reset);
    pack.addEventListener("click", config.handle.toggle);
    test.addEventListener("click", config.handle.background);
    support.addEventListener("click", config.handle.background);
    tutorial.addEventListener("click", config.handle.background);
    donation.addEventListener("click", config.handle.background);
    /*  */
    config.elements.custom = document.getElementById("custom");
    config.elements.cookie = document.getElementById("cookie");
    config.elements.overlay = document.querySelector(".overlay");
    config.elements.fontsize = document.getElementById("fontsize");
    config.elements.reset = document.getElementById("reset-addon");
    config.elements.support = document.getElementById("opensupport");
    config.elements.whitelist = document.getElementById("whitelist");
    config.elements.scheduleon = document.getElementById("scheduleon");
    config.elements.scheduleoff = document.getElementById("scheduleoff");
    config.elements.toggleaction = document.getElementById("toggleaction");
    config.elements.documentroot = document.getElementById("documentroot");
    config.elements.nativeinline = document.getElementById("nativeinline");
    config.elements.nativeignore = document.getElementById("nativeignore");
    config.elements.nativerecheck = document.getElementById("nativerecheck");
    config.elements.nativerespect = document.getElementById("nativerespect");
    config.elements.inclusivelist = document.getElementById("inclusivelist");
    config.elements.excludeiframes = document.getElementById("excludeiframes");
    config.elements.scheduleaction = document.getElementById("scheduleaction");
    config.elements.nativecssrules = document.getElementById("nativecssrules");
    config.elements.nativecontinue = document.getElementById("nativecontinue");
    config.elements.nativepriority = document.getElementById("nativepriority");
    config.elements.nativesupports = document.getElementById("nativesupports");
    config.elements.nativedeeprules = document.getElementById("nativedeeprules");
    config.elements.nativekeyframes = document.getElementById("nativekeyframes");
    config.elements.nativeclassname = document.getElementById("nativeclassname");
    config.elements.inclusiveaction = document.getElementById("inclusiveaction");
    config.elements.mapcssvariables = document.getElementById("mapcssvariables");
    config.elements.nativeforcefont = document.getElementById("nativeforcefont");
    config.elements.checkstylesheet = document.getElementById("checkstylesheet");
    config.elements.nativemediaquery = document.getElementById("nativemediaquery");
    config.elements.nativecompatible = document.getElementById("nativecompatible");
    config.elements.excludeclassnames = document.getElementById("excludeclassnames");
    config.elements.excludeattributes = document.getElementById("excludeattributes");
    config.elements.nativeremoveimage = document.getElementById("nativeremoveimage");
    config.elements.nativeremovecolor = document.getElementById("nativeremovecolor");
    config.elements.nativedarkenimage = document.getElementById("nativedarkenimage");
    config.elements.nativeforceborder = document.getElementById("nativeforceborder");
    config.elements.nativeforcesvgfill = document.getElementById("nativeforcesvgfill");
    config.elements.nativebestpageload = document.getElementById("nativebestpageload");
    config.elements.nativecssstylesheet = document.getElementById("nativecssstylesheet");
    config.elements.nativerangelimitmin = document.getElementById("nativerangelimitmin");
    config.elements.nativerangelimitmax = document.getElementById("nativerangelimitmax");
    config.elements.nativerechecktimeout = document.getElementById("nativerechecktimeout");
    config.elements.nativeforcesvgstroke = document.getElementById("nativeforcesvgstroke");
    config.elements.nativeforceboxshadow = document.getElementById("nativeforceboxshadow");
    config.elements.nativedarkenvariable = document.getElementById("nativedarkenvariable");
    config.elements.excludecsscolorscheme = document.getElementById("excludecsscolorscheme");
    config.elements.nativebackgroundblend = document.getElementById("nativebackgroundblend");
    config.elements.nativebestperformance = document.getElementById("nativebestperformance");
    config.elements.nativeforcebackground = document.getElementById("nativeforcebackground");
    config.elements.nativeforcetextshadow = document.getElementById("nativeforcetextshadow");
    config.elements.excludedarkbackground = document.getElementById("excludedarkbackground");
    config.elements.nativeforceborderwidth = document.getElementById("nativeforceborderwidth");
    config.elements.nativecssvariables = [...document.querySelectorAll(".cssvariables input")];
    config.elements.excludemetacolorscheme = document.getElementById("excludemetacolorscheme");
    config.elements.nativeforceclosetowhite = document.getElementById("nativeforceclosetowhite");
    config.elements.nativebackgroundrelated = document.getElementById("nativebackgroundrelated");
    config.elements.nativebackgroundinitial = document.getElementById("nativebackgroundinitial");
    config.elements.nativeforcetransparency = document.getElementById("nativeforcetransparency");
    config.elements.nativerangethresholdmin = document.getElementById("nativerangethresholdmin");
    config.elements.nativerangethresholdmax = document.getElementById("nativerangethresholdmax");
    config.elements.nativebackgroundfallback = document.getElementById("nativebackgroundfallback");
    config.elements.excludeincolorschemedark = document.getElementById("excludeincolorschemedark");
    config.elements.nativeperformanceobserver = document.getElementById("nativeperformanceobserver");
    config.elements.nativeforcebackgroundcolor = document.getElementById("nativeforcebackgroundcolor");
    config.elements.nativeforceclosetowhitemin = document.getElementById("nativeforceclosetowhitemin");
    config.elements.nativeforceclosetowhitemax = document.getElementById("nativeforceclosetowhitemax");
    config.elements.excludedarkbackgroundnative = document.getElementById("excludedarkbackgroundnative");
    config.elements.nativebackgroundtransparency = document.getElementById("nativebackgroundtransparency");
    config.elements.nativeforceclosetowhitepercent = document.getElementById("nativeforceclosetowhitepercent");
    config.elements.excludedarkbackgroundthreshold = document.getElementById("excludedarkbackgroundthreshold");
    /*  */
    config.elements.nativedarkengradient = {};
    config.elements.nativedarkengradient.action = document.getElementById("nativedarkengradient");
    config.elements.nativedarkengradient.darkshade = document.getElementById("nativedarkenshade");
    config.elements.nativedarkengradient.fieldset = document.getElementById("nativedarkengradient-fieldset");
    /*  */
    config.elements.temporarily = {};
    config.elements.temporarily.delay = document.getElementById("temporarilydelay");
    config.elements.temporarily.action = document.getElementById("temporarilyaction");
    config.elements.temporarily.display = document.getElementById("temporarilydisplay");
    config.elements.temporarily.threshold = document.getElementById("temporarilythreshold");
    config.elements.temporarily.brightness = document.getElementById("temporarilybrightness");
    config.elements.temporarily.simpledark = document.getElementById("temporarilysimpledark");
    config.elements.temporarily.fieldset = document.getElementById("temporarilyaction-fieldset");
    /*  */
    config.elements.nativecolorful = {};
    config.elements.nativecolorful.action = document.getElementById("nativecolorful");
    config.elements.nativecolorful.svg = document.getElementById("nativecolorful-svg");
    config.elements.nativecolorful.font = document.getElementById("nativecolorful-font");
    config.elements.nativecolorful.border = document.getElementById("nativecolorful-border");
    config.elements.nativecolorful.fieldset = document.getElementById("nativecolorful-fieldset");
    config.elements.nativecolorful.background = document.getElementById("nativecolorful-background");
    /*  */
    config.elements.colortemperature = {};
    config.elements.colortemperature.output = {};
    config.elements.colortemperature.action = document.getElementById("colortemperature");
    config.elements.colortemperature.red = document.getElementById("colortemperature-red");
    config.elements.colortemperature.blue = document.getElementById("colortemperature-blue");
    config.elements.colortemperature.green = document.getElementById("colortemperature-green");
    config.elements.colortemperature.opacity = document.getElementById("colortemperature-opacity");
    config.elements.colortemperature.fieldset = document.getElementById("colortemperature-fieldset");
    config.elements.colortemperature.whitelist = document.getElementById("colortemperature-whitelist");
    config.elements.colortemperature.output.red = document.getElementById("colortemperature-red").closest("label").querySelector("output");
    config.elements.colortemperature.output.blue = document.getElementById("colortemperature-blue").closest("label").querySelector("output");
    config.elements.colortemperature.output.green = document.getElementById("colortemperature-green").closest("label").querySelector("output");
    config.elements.colortemperature.output.opacity = document.getElementById("colortemperature-opacity").closest("label").querySelector("output");
    /*  */
    config.elements.custom.addEventListener("keyup", config.handle.store);
    config.elements.support.addEventListener("change", config.handle.store);
    config.elements.overlay.addEventListener("click", config.handle.toggle);
    config.elements.fontsize.addEventListener("change", config.handle.store);
    config.elements.reset.addEventListener("click", config.handle.background);
    config.elements.scheduleon.addEventListener("change", config.handle.store);
    config.elements.scheduleoff.addEventListener("change", config.handle.store);
    config.elements.toggleaction.addEventListener("change", config.handle.store);
    config.elements.documentroot.addEventListener("change", config.handle.store);
    config.elements.nativeinline.addEventListener("change", config.handle.store);
    config.elements.nativeignore.addEventListener("change", config.handle.store);
    config.elements.nativerecheck.addEventListener("change", config.handle.store);
    config.elements.nativerespect.addEventListener("change", config.handle.store);
    config.elements.nativecssrules.addEventListener("keyup", config.handle.store);
    config.elements.excludeiframes.addEventListener("change", config.handle.store);
    config.elements.nativecontinue.addEventListener("change", config.handle.store);
    config.elements.nativepriority.addEventListener("change", config.handle.store);
    config.elements.scheduleaction.addEventListener("change", config.handle.store);
    config.elements.nativesupports.addEventListener("change", config.handle.store);
    config.elements.nativedeeprules.addEventListener("change", config.handle.store);
    config.elements.nativekeyframes.addEventListener("change", config.handle.store);
    config.elements.checkstylesheet.addEventListener("change", config.handle.store);
    config.elements.nativeclassname.addEventListener("change", config.handle.store);
    config.elements.mapcssvariables.addEventListener("change", config.handle.store);
    config.elements.inclusiveaction.addEventListener("change", config.handle.store);
    config.elements.nativeforcefont.addEventListener("change", config.handle.store);
    config.elements.nativemediaquery.addEventListener("change", config.handle.store);
    config.elements.nativecompatible.addEventListener("change", config.handle.store);
    config.elements.temporarily.delay.addEventListener("change", config.handle.store);
    config.elements.nativeremoveimage.addEventListener("change", config.handle.store);
    config.elements.nativeremovecolor.addEventListener("change", config.handle.store);
    config.elements.nativedarkenimage.addEventListener("change", config.handle.store);
    config.elements.nativeforceborder.addEventListener("change", config.handle.store);
    config.elements.nativebestpageload.addEventListener("change", config.handle.store);
    config.elements.nativeforcesvgfill.addEventListener("change", config.handle.store);
    config.elements.temporarily.action.addEventListener("change", config.handle.store);
    config.elements.temporarily.display.addEventListener("change", config.handle.store);
    config.elements.nativecssstylesheet.addEventListener("change", config.handle.store);
    config.elements.nativerangelimitmin.addEventListener("change", config.handle.store);
    config.elements.nativerangelimitmax.addEventListener("change", config.handle.store);
    config.elements.nativerechecktimeout.addEventListener("change", config.handle.store);
    config.elements.nativeforceboxshadow.addEventListener("change", config.handle.store);
    config.elements.nativedarkenvariable.addEventListener("change", config.handle.store);
    config.elements.nativeforcesvgstroke.addEventListener("change", config.handle.store);
    config.elements.excludecsscolorscheme.addEventListener("change", config.handle.store);
    config.elements.temporarily.threshold.addEventListener("change", config.handle.store);
    config.elements.nativebackgroundblend.addEventListener("change", config.handle.store);
    config.elements.nativeforcetextshadow.addEventListener("change", config.handle.store);
    config.elements.nativeforcebackground.addEventListener("change", config.handle.store);
    config.elements.nativebestperformance.addEventListener("change", config.handle.store);
    config.elements.excludedarkbackground.addEventListener("change", config.handle.store);
    config.elements.excludemetacolorscheme.addEventListener("change", config.handle.store);
    config.elements.temporarily.brightness.addEventListener("change", config.handle.store);
    config.elements.temporarily.simpledark.addEventListener("change", config.handle.store);
    config.elements.nativeforceborderwidth.addEventListener("change", config.handle.store);
    config.elements.nativebackgroundrelated.addEventListener("change", config.handle.store);
    config.elements.nativebackgroundinitial.addEventListener("change", config.handle.store);
    config.elements.nativeforcetransparency.addEventListener("change", config.handle.store);
    config.elements.nativerangethresholdmin.addEventListener("change", config.handle.store);
    config.elements.nativerangethresholdmax.addEventListener("change", config.handle.store);
    config.elements.nativeforceclosetowhite.addEventListener("change", config.handle.store);
    config.elements.excludeincolorschemedark.addEventListener("change", config.handle.store);
    config.elements.nativebackgroundfallback.addEventListener("change", config.handle.store);
    config.elements.nativeperformanceobserver.addEventListener("change", config.handle.store);
    config.elements.nativeforcebackgroundcolor.addEventListener("change", config.handle.store);
    config.elements.nativeforceclosetowhitemin.addEventListener("change", config.handle.store);
    config.elements.nativeforceclosetowhitemax.addEventListener("change", config.handle.store);
    config.elements.nativedarkengradient.action.addEventListener("change", config.handle.store);
    config.elements.excludedarkbackgroundnative.addEventListener("change", config.handle.store);
    config.elements.nativebackgroundtransparency.addEventListener("change", config.handle.store);
    config.elements.nativedarkengradient.darkshade.addEventListener("change", config.handle.store);
    config.elements.excludedarkbackgroundthreshold.addEventListener("change", config.handle.store);
    config.elements.nativeforceclosetowhitepercent.addEventListener("change", config.handle.store);
    config.elements.nativecssvariables.map(function (e) {e.addEventListener("change", config.handle.store)});
    /*  */
    config.elements.nativecolorful.svg.addEventListener("change", config.handle.store);
    config.elements.nativecolorful.font.addEventListener("change", config.handle.store);
    config.elements.nativecolorful.action.addEventListener("change", config.handle.store);
    config.elements.nativecolorful.border.addEventListener("change", config.handle.store);
    config.elements.nativecolorful.background.addEventListener("change", config.handle.store);
    /*  */
    config.elements.colortemperature.red.addEventListener("input", config.handle.store);
    config.elements.colortemperature.blue.addEventListener("input", config.handle.store);
    config.elements.colortemperature.green.addEventListener("input", config.handle.store);
    config.elements.colortemperature.action.addEventListener("input", config.handle.store);
    config.elements.colortemperature.opacity.addEventListener("input", config.handle.store);
    /*  */
    items.map(function (e) {e.addEventListener("click", config.handle.background)});
    items.map(function (e) {e.addEventListener("mouseenter", config.handle.mouseenter)});
    items.map(function (e) {e.addEventListener("mouseleave", config.handle.mouseleave)});
    /*  */
    config.style.textarea["textarea"] = config.elements.custom;
    new Behave(config.style.textarea);
    /*  */
    config.style.textarea["textarea"] = config.elements.nativecssrules;
    new Behave(config.style.textarea);
    /*  */
    if (window.PerformanceLongTaskTiming === undefined) {
      const label = config.elements.nativebestpageload.closest("label");
      if (label) {
        label.setAttribute("disabled", '');
      }
    }
    /*  */
    for (let name in website.custom.regex.rules) {
      let element = document.getElementById(name);
      if (element) {
        element.addEventListener("click", config.handle.click);
      }
    }
    /*  */
    for (let i = 1; i <= website.total.themes.number; i++) {
      let element = document.getElementById("dark_" + i);
      if (element) {
        element.addEventListener("click", config.handle.click);
      }
    }
    /*  */
    for (let i = 0; i < website.custom.compatible.length; i++) {
      let name = website.custom.compatible[i];
      let element = document.getElementById(name);
      if (element) {
        element.closest("label").setAttribute("compatible", '');
      }
    }
    /*  */
    config.elements.cookie.addEventListener("change", function () {
      let tmp = [];
      let cookie = config.elements.cookie.value || '';
      let splitted = cookie.split(/\s*\,\s*/);
      /*  */
      for (let i = 0; i < splitted.length; i++) tmp.push(splitted[i]);
      tmp = tmp.filter(function (element, index, array) {return element && array.indexOf(element) === index});
      chrome.storage.local.set({"cookie": tmp});
    });
    /*  */
    summary.map(function (element) {
      element.addEventListener("click", function (e) {
        let tmp = {};
        let value = !e.target.closest("details").open;
        let name = e.target.closest("details").className;
        /*  */
        tmp[name] = value;
        chrome.storage.local.set(tmp);
      });
    });
    /*  */
    config.elements.excludeclassnames.addEventListener("change", function () {
      let tmp = [];
      let excludeclassnames = config.elements.excludeclassnames.value || '';
      let splitted = excludeclassnames.split(/\s*\,\s*/);
      /*  */
      for (let i = 0; i < splitted.length; i++) {
        tmp.push(splitted[i]);
      }
      /*  */
      tmp = tmp.filter(function (element, index, array) {return element && array.indexOf(element) === index});
      chrome.storage.local.set({"excludeclassnames": tmp});
    });
    /*  */
    config.elements.excludeattributes.addEventListener("change", function () {
      let tmp = [];
      let excludeattributes = config.elements.excludeattributes.value || '';
      let splitted = excludeattributes.split(/\s*\,\s*/);
      /*  */
      for (let i = 0; i < splitted.length; i++) {
        tmp.push(splitted[i]);
      }
      /*  */
      tmp = tmp.filter(function (element, index, array) {return element && array.indexOf(element) === index});
      chrome.storage.local.set({"excludeattributes": tmp});
    });
    /*  */
    config.elements.whitelist.addEventListener("change", function () {
      let tmp = [];
      let whitelist = config.elements.whitelist.value || '';
      let splitted = whitelist.split(/\s*\,\s*/);
      /*  */
      for (let i = 0; i < splitted.length; i++) {
        const hostname = config.hostname(splitted[i]);
        tmp.push(hostname ? hostname : splitted[i]);
      }
      /*  */
      tmp = tmp.filter(function (element, index, array) {return element && array.indexOf(element) === index});
      chrome.storage.local.set({"whitelist": tmp});
    });
    /*  */
    config.elements.colortemperature.whitelist.addEventListener("change", function () {
      let tmp = [];
      let whitelist = config.elements.colortemperature.whitelist.value || '';
      let splitted = whitelist.split(/\s*\,\s*/);
      /*  */
      for (let i = 0; i < splitted.length; i++) {
        const hostname = config.hostname(splitted[i]);
        tmp.push(hostname ? hostname : splitted[i]);
      }
      /*  */
      tmp = tmp.filter(function (element, index, array) {return element && array.indexOf(element) === index});
      chrome.storage.local.set({"colortemperature-whitelist": tmp});
    });
    /*  */
    config.elements.inclusivelist.addEventListener("change", function () {
      let tmp = [];
      let inclusivelist = config.elements.inclusivelist.value || '';
      let splitted = inclusivelist.split(/\s*\,\s*/);
      /*  */
      for (let i = 0; i < splitted.length; i++) {
        const hostname = config.hostname(splitted[i]);
        tmp.push(hostname ? hostname : splitted[i]);
      }
      /*  */
      tmp = tmp.filter(function (element, index, array) {return element && array.indexOf(element) === index});
      chrome.storage.local.set({"inclusivelist": tmp});
    });
    /*  */
    chrome.storage.onChanged.addListener(function (e) {
      if (Object.keys(e).length > 10) {
        if (config.interface.timeout) window.clearTimeout(config.interface.render);
        config.interface.timeout = window.setTimeout(config.interface.render, 300);
      } else {
        config.interface.render();
      }
    });
    /*  */
    config.interface.render();
    window.removeEventListener("load", config.load, false);
  }
};

window.addEventListener("load", config.load, false);
