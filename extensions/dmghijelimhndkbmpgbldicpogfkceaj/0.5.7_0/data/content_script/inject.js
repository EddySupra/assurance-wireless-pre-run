var background = (function () {
  let tmp = {};
  /*  */
  chrome.runtime.onMessage.addListener(function (request) {
    for (let id in tmp) {
      if (tmp[id] && (typeof tmp[id] === "function")) {
        if (request.path === "background-to-page") {
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
        "path": "page-to-background"
      }, function () {
        return chrome.runtime.lastError;
      });
    }
  }
})();

var config = {
  "log": false,
  "current": {},
  "addon": {
    "state": null
  },
  "general": {
    "link": document.getElementById("dark-mode-general-link")
  },
  "custom": {
    "link": document.getElementById("dark-mode-custom-link"),
    "style": document.getElementById("dark-mode-custom-style")
  },
  "start": function () {
    chrome.storage.local.get(null, config.render.pre);
    config.observer.storage();
  },
  "content": function (e) {
    if (e) {
      native.dark.engine.process.remote.style(e);
    }
  },
  "observer": {
    "storage": function () {
      chrome.storage.onChanged.addListener(function () {
        background.send("reload");
      });
    },
    "head": new MutationObserver(function () {
      let parent = config.native.documentroot ? document.documentElement : document.head;
      if (parent) {
        config.check.darkmode.nodes(0);
        config.observer.head.disconnect();
      }
    })
  },
  "hostname": function (url) {
    try {
      url = url.replace("www.", '');
      let s = url.indexOf("//") + 2;
      if (s > 1) {
        let o = url.indexOf('/', s);
        if (o > 0) return url.substring(s, o);
        else {
          o = url.indexOf('?', s);
          if (o > 0) return url.substring(s, o);
          else return url.substring(s);
        }
      } else {
        return url;
      }
    } catch (e) {
      return url;
    }
  },
  "load": function () {
    config.observer.head.disconnect();
    /*  */
    if (config.temporarily.is.removed === false) {
      const delay = config.native.temporarily.delay !== undefined ? Number(config.native.temporarily.delay) : 200;
      //
      config.temporarily.is.removed = true;
      config.temporarily.remove(delay, 5);
    }
    /*  */
    if (config.addon.state === "dark") {
      if (config.native.recheck) {
        const timeout = config.native.rechecktimeout !== undefined ? Number(config.native.rechecktimeout) : 0;
        //
        window.setTimeout(function () {
          background.send("recheck");
        }, timeout);
      } else {
        const darkness = config.check.darkness(null);
        const darkcolor = config.check.darkcolor.page(1);
        const attribute = document.documentElement.getAttribute(native.dark.attribute.theme);
        /*  */
        if (darkcolor) {
          config.style.remove(1);
        } else {
          if (darkness) {
            config.native.darkness = darkness;
            config.style.clear(null, 7);
          } else {
            if (attribute === null) {
              document.documentElement.setAttribute(native.dark.attribute.theme, '');
            }
            /*  */
            //config.check.darkmode.nodes(2);
            //native.dark.engine.analyze.document.sheets("process", 3);
          }
        }
      }
    }
    /*  */
    window.removeEventListener("load", config.load, false);
  },
  "message": function (e) {
    if (e) {
      if (e.data) {
        if (e.data.from) {
          if (e.data.from === "native-dark-context-shadownode") {
            if (config.native.shadow.timeout) window.clearTimeout(config.native.shadow.timeout);
            config.native.shadow.timeout = window.setTimeout(function () {
              config.native.shadow.find.stylesheets(document.documentElement);
            }, 100);
          }
          //
          if (e.data.from === "native-dark-context-top-for-exclude") {
            if (e.data.darkness === true) {
              const options = {"frameId": e.data.frameId};
              config.style.clear(options, 8);
            }
          }
          //
          if (e.data.from === "native-dark-context-iframe-for-exclude") {
            if (e.source) {
              if (e.source.postMessage) {
                e.source.postMessage({
                  "frameId": e.data.frameId,
                  "darkness": config.native.darkness,
                  "from": "native-dark-context-top-for-exclude"
                }, '*');
              }
            }
          }
        }
      }
    }
  },
  "temporarily": {
    "timeout": undefined,
    "is": {
      "slow": false,
      "removed": false,
    },
    "id": {
      "start": "temporarily-dark-start",
      "display": "temporarily-dark-display",
      "simpledark": "temporarily-dark-simple",
      "brightness": "temporarily-dark-brightness"
    },
    "add": function (attribute) {
      if (document.documentElement) {
        document.documentElement.setAttribute(attribute, '');
      }
    },
    "remove": function (delay, loc) {
      if (document.documentElement) {
        if (config.log) {
          console.error(loc);
        }
        //
        if (delay) {
          if (config.temporarily.timeout) window.clearTimeout(config.temporarily.timeout);
          config.temporarily.timeout = window.setTimeout(function () {
            document.documentElement.removeAttribute(config.temporarily.id.start);
            document.documentElement.removeAttribute(config.temporarily.id.display);
            document.documentElement.removeAttribute(config.temporarily.id.simpledark);
            document.documentElement.removeAttribute(config.temporarily.id.brightness);
          }, delay);
        } else {
          document.documentElement.removeAttribute(config.temporarily.id.start);
          document.documentElement.removeAttribute(config.temporarily.id.display);
          document.documentElement.removeAttribute(config.temporarily.id.simpledark);
          document.documentElement.removeAttribute(config.temporarily.id.brightness);
        }
      }
    }
  },
  "convert": {
    "color": {
      "to": {
        "rgba": function (value) {
          try {
            if (!value) return null;
            if (/^rgba?\(\s*\d+/.test(value)) return value;
            /*  */
            const tmp = document.createElement("div");
            tmp.style.color = value;
            tmp.style.display = "none";
            document.body.appendChild(tmp);
            /*  */
            const computed = window.getComputedStyle(tmp).color;
            tmp.remove();
            /*  */
            if (/^rgba?\(\s*\d+/.test(computed)) {
              return computed;
            } else {
              const canvas = document.createElement("canvas");
              canvas.width = 1;
              canvas.height = 1;
              const ctx = canvas.getContext("2d");
              /*  */
              ctx.fillStyle = computed;
              ctx.fillRect(0, 0, 1, 1);
              /*  */
              const imagedata = ctx.getImageData(0, 0, 1, 1).data;
              return imagedata && imagedata.length ? `rgba(${imagedata[0]}, ${imagedata[1]}, ${imagedata[2]}, ${imagedata[3] / 255})` : null;
            }
          } catch (e) {
            if (config.log) {
              console.error(e);
            }
            //
            return null;
          }
          //
          return null;
        }
      }
    }
  },
  "colortemperature": {
    "hostname": '',
    "whitelist": [],
    "remove": function () {
      const overlay = document.querySelector(".colortemperature-overlay");
      /*  */
      document.documentElement.removeAttribute("color-temperature");
      if (overlay) overlay.remove();
    },
    "render": function (e) {
      const red = e.storage["colortemperature-red"];
      const blue = e.storage["colortemperature-blue"];
      const green = e.storage["colortemperature-green"];
      const opacity = e.storage["colortemperature-opacity"];
      /*  */
      if (window === window.top) {
        const overlay = document.querySelector(".colortemperature-overlay");
        /*  */
        if ("top" in e) config.colortemperature.hostname = (new URL(e.top).hostname).replace("www.", '');
        if ("colortemperature-whitelist" in e.storage) config.colortemperature.whitelist = e.storage["colortemperature-whitelist"];
        /*  */
        if (overlay) overlay.remove();
        document.documentElement.removeAttribute("color-temperature");
        document.documentElement.style.removeProperty("--colortemperature-red");
        document.documentElement.style.removeProperty("--colortemperature-blue");
        document.documentElement.style.removeProperty("--colortemperature-green");
        document.documentElement.style.removeProperty("--colortemperature-opacity");
        /*  */
        const action = config.colortemperature.hostname ? config.colortemperature.whitelist.indexOf(config.colortemperature.hostname) === -1 : true;
        if (action) {
          const overlay = document.createElement("div");
          overlay.setAttribute("class", "colortemperature-overlay");
          /*  */
          document.documentElement.setAttribute("color-temperature", '');
          document.documentElement.style.setProperty("--colortemperature-red", red);
          document.documentElement.style.setProperty("--colortemperature-blue", blue);
          document.documentElement.style.setProperty("--colortemperature-green", green);
          document.documentElement.style.setProperty("--colortemperature-opacity", opacity / 100);
          document.documentElement.insertBefore(overlay, document.documentElement.firstChild);
        }
      }
    }
  },
  "check": {
    "darkness": function (e) {
      if (e) config.native.darknessstorage = e;
      /*  */
      const cookies = config.native.darknessstorage.cookie;
      const excludeclassnames = config.native.darknessstorage.excludeclassnames;
      const excludeattributes = config.native.darknessstorage.excludeattributes;
      const excludemetacolorscheme = config.native.darknessstorage.excludemetacolorscheme;
      const iscolorschemedark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      const action = config.native.excludeincolorschemedark ? iscolorschemedark : true;
      /*  */
      if (action) {
        try {
          const body = document.body || null;
          const html = document.documentElement;
          const escaped = excludeclassnames.map(str => str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
          const meta = document.querySelector && document.querySelector('meta[name="color-scheme"]');
          const pattern = escaped && escaped.length ? "(?<![a-z0-9-])(" + escaped.join('|') + ")(?![a-z0-9-])" : null;
          const darkclassnames = pattern ? new RegExp(pattern, 'i') : null;
          //
          if (excludemetacolorscheme) {
            if (meta && /dark/i.test(meta.getAttribute("content") || '')) {            
              return true;
            }
          }
          //
          if (darkclassnames) {
            if (darkclassnames.test(html.className || '') || (body && darkclassnames.test(body.className || ''))) {
              return true;
            }
          }
          //
          for (const name of excludeattributes) {
            const attribute = (html.getAttribute && html.getAttribute(name)) || (body && body.getAttribute && body.getAttribute(name));
            if (attribute) {
              if (attribute !== "light dark" && attribute !== "dark light") {
                if (darkclassnames.test(attribute)) {
                  return true;
                }
              }
            }
          }
        } catch (e) {
          if (config.log) {
            console.error(e);
          }
        }
        /*  */
        try {
          if (cookies && cookies.length) {
            for (let i = 0; i < cookies.length; i++) {
              if (document.cookie) {
                if (document.cookie.indexOf(cookies[i]) !== -1) {
                  return true;
                }
              }
              /*  */
              if (localStorage) {
                for (let j = 0; j < localStorage.length; j++) {
                  const key = localStorage.key(j);
                  if (key.indexOf(cookies[i]) !== -1) {
                    return true;
                  }
                }
              }
              /*  */
              if (sessionStorage) {
                for (let j = 0; j < sessionStorage.length; j++) {
                  const key = sessionStorage.key(j);
                  if (key.indexOf(cookies[i]) !== -1) {
                    return true;
                  }
                }
              }
            }
          }
        } catch (e) {
          if (config.log) {
            console.error(e);
          }
        }
      }
      /*  */
      return false;
    },
    "darkmode": {
      "nodes": function (loc) {
        let tmp = {};
        let parent = config.native.documentroot ? document.documentElement : document.head;
        /*  */
        if (parent) {
          tmp.a = document.getElementById("dark-mode-general-link");
          if (!tmp.a) {
            parent.appendChild(config.general.link);
          }
          /*  */
          tmp.b = document.getElementById("dark-mode-custom-link");
          if (!tmp.b) {
            parent.appendChild(config.custom.link);
          }
          /*  */
          tmp.c = document.getElementById("dark-mode-custom-style");
          if (!tmp.c) {
            parent.appendChild(config.custom.style);
          }
          /*  */
          tmp.d = document.getElementById("dark-mode-native-style");
          if (!tmp.d) {
            parent.appendChild(config.native.style);        
          }
          /*  */
          tmp.d = document.getElementById("dark-mode-native-sheet");
          if (!tmp.d) {
            parent.appendChild(config.native.sheet);
            //
            if (config.native.stylesheet === null) {
              config.native.stylesheet = config.native.sheet.sheet;
              background.send("load");
            }
          }
        }
      },
      "native": {
        "styles": function (loc) {
          if (config.native.style) {
            if (!config.native.style.parentNode) { // style is removed!
              document.documentElement.appendChild(config.native.style);
              //
              if (config.log) {
                console.error("re-attaching the native style to the root!", loc);
              }
            }
          }
          //
          if (config.native.sheet) {
            if (!config.native.sheet.parentNode) { // sheet is removed!
              if (config.native.stylesheet) {
                if (!config.native.stylesheet.ownerNode) {
                  if (config.native.stylesheet.cssRules) {
                    if (config.native.stylesheet.cssRules.length) {
                      let rulesText = '';
                      for (let i = 0; i < config.native.stylesheet.cssRules.length; i++) {
                        rulesText += config.native.stylesheet.cssRules[i].cssText + '\n';
                      }
                      //
                      if (rulesText) {
                        config.native.sheet.textContent = rulesText;
                        document.documentElement.appendChild(config.native.sheet);
                        //
                        if (config.native.sheet.sheet) {
                          config.native.stylesheet = config.native.sheet.sheet;
                        } else {
                          window.requestAnimationFrame(function () {
                            config.native.stylesheet = config.native.sheet.sheet;
                          });
                        }
                        //
                        if (config.log) {
                          console.error("re-attaching the native sheet to the root!", loc);
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    },
    "darkcolor": {
      "rgba": function (e, t) {
        if (!e) {
          return {
            "target": e,
            "result": false,
          };
        }
        /*  */
        const cond_1 = e === "transparent";
        const cond_2 = e === "rgba(0, 0, 0, 0)";
        /*  */
        if (cond_1 || cond_2) {
          return {
            "target": e,
            "result": false
          };
        }
        /*  */
        const values = e.match(/\d+/g);
        if (!values || values.length < 3) {
          return {
            "result": false, 
            "target": values
          };
        }
        /*  */
        const [r, g, b] = values.map(Number);
        const brightness = (r * 299 + g * 587 + b * 114) / 1000;
        /*  */
        return {
          "target": e,
          "result": brightness < Number(t)
        };
      },
      "page": function (loc) {
        const iscolorschemedark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        const action = config.native.excludeincolorschemedark ? iscolorschemedark : true;
        /*  */
        if (action) {
          if (config.native.excludecsscolorscheme || config.native.excludedarkbackground) {
            try {
              const sheets = document.styleSheets;
              const rules = {"style": [], "media": []};
              const threshold = config.native.excludedarkbackgroundthreshold;
              /*  */
              rules.check = function (rule, scheme) {
                const text = rule.selectorText;
                if (text) {
                  if (text.includes("html") || text.includes("body") || text.includes(":root")) {
                    const conds = {};
                    const selectors = text.split(',');
                    /*  */
                    conds.scheme = scheme;
                    conds.html = selectors.some(e => e.trim() === "html");
                    conds.body = selectors.some(e => e.trim() === "body");
                    conds.root = selectors.some(e => e.trim() === ":root");
                    /*  */
                    if (config.native.excludecsscolorscheme) {
                      if ((conds.html || conds.root) && conds.scheme) {
                        const value = rule.style.getPropertyValue("color-scheme").trim();
                        if (value === "dark") {
                          return true;
                        }
                      }
                    }
                    /*  */
                    if (config.native.excludedarkbackground) {
                      const exclude = config.native.excludedarkbackgroundnative ? native.dark.engine.is.active : true;
                      if (exclude) {
                        if (conds.html || conds.body) {
                          const color = config.convert.color.to.rgba(rule.style.backgroundColor || rule.style.getPropertyValue("background-color"));
                          if (color) {
                            const flag = config.check.darkcolor.rgba(color, threshold);
                            if (flag) {
                              return flag.result;
                            }
                          }
                        }
                      }
                    }
                  }
                }
                /*  */
                return false;
              }
              /*  */
              if (sheets) {
                for (const sheet of sheets) {
                  if (sheet.ownerNode) {
                    const conds = [];
                    const id = sheet.ownerNode.id;
                    const name = sheet.ownerNode.className;
                    /*  */
                    conds[0] = id !== "dark-mode-custom-link";
                    conds[1] = id !== "dark-mode-general-link";
                    conds[2] = id !== "dark-mode-custom-style";
                    conds[3] = id !== "dark-mode-native-style";
                    conds[4] = id !== "dark-mode-native-sheet";
                    conds[5] = name !== native.dark.class.original;
                    conds[6] = name !== native.dark.class.processed;
                    /*  */
                    if (conds.every(Boolean)) {
                      try {
                        rules.style = sheet.cssRules;
                      } catch (e) {}
                      /*  */
                      for (const rule of rules.style) {
                        if (rule) {
                          if (rule.selectorText) {
                            if (rules.check(rule, false)) {
                              return true;
                            }
                          }
                          /*  */
                          if (rule.conditionText) {
                            const condition = rule.conditionText.trim();
                            if (iscolorschemedark && condition === "(prefers-color-scheme: dark)") {
                              try {
                                rules.media = rule.cssRules;
                              } catch (e) {}
                              /*  */
                              for (const rule of rules.media) {
                                if (rule) {
                                  if (rules.check(rule, true)) {
                                    return true;
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            } catch (e) {
              return false;
            }
          }
        }
        /*  */
        return false;
      }
    }
  },
  "style": {
    "remove": function (loc) {
      try {
        config.style.clear(null, 0);
        //
        document.documentElement.removeAttribute("color-temperature");
        document.documentElement.removeAttribute(native.dark.attribute.theme);
        document.documentElement.removeAttribute(config.temporarily.id.start);
        document.documentElement.removeAttribute(config.temporarily.id.display);
        document.documentElement.removeAttribute(config.temporarily.id.simpledark);
        document.documentElement.removeAttribute(config.temporarily.id.brightness);
        //
        if (native.dark.observer.style.mutation) native.dark.observer.style.mutation.disconnect();
        if (native.dark.observer.element.mutation) native.dark.observer.element.mutation.disconnect();
        if (native.dark.observer.classname.mutation) native.dark.observer.classname.mutation.disconnect();
        if (native.dark.observer.performance.long.mutation) native.dark.observer.performance.long.mutation.disconnect();
        if (native.dark.observer.performance.short.mutation) native.dark.observer.performance.short.mutation.disconnect();
        //
        config.custom.link.remove();
        config.native.sheet.remove();
        config.custom.style.remove();
        config.native.style.remove();
        config.general.link.remove();
        //
        config.native.sheet.disabled = true;
        native.dark.engine.is.active = false;
        //
        native.dark.engine.analyze.document.sheets("clean", 5);
        if (config.native.cssstylesheet) {
          config.native.shadow.toggle.stylesheets({"disabled": true});
        }
      } catch (e) {
        if (config.log) {
          console.error(e);
        }
      }
    },
    "clear": function (e, loc) {
      try {
        if (e) {
          if ("reload" in e) config.current.reload = e.reload;
          if ("frameId" in e) config.current.frameId = e.frameId;
        }
        /*  */
        if (config.current.frameId === 0) {
          if (config.current.reload === false) {
            config.temporarily.remove(0, loc);
          }
        }
        //
        document.documentElement.removeAttribute(native.dark.attribute.theme);
        document.documentElement.removeAttribute(config.temporarily.id.start);
        //
        if (native.dark.observer.style.mutation) native.dark.observer.style.mutation.disconnect();
        if (native.dark.observer.element.mutation) native.dark.observer.element.mutation.disconnect();
        if (native.dark.observer.classname.mutation) native.dark.observer.classname.mutation.disconnect();
        if (native.dark.observer.performance.long.mutation) native.dark.observer.performance.long.mutation.disconnect();
        if (native.dark.observer.performance.short.mutation) native.dark.observer.performance.short.mutation.disconnect();
        //
        config.native.sheet.disabled = true;
        native.dark.engine.is.active = false;
        config.custom.style.textContent = '';
        config.native.style.textContent = '';
        config.custom.link.removeAttribute("href");
        config.general.link.removeAttribute("href");
        //
        native.dark.engine.analyze.document.sheets("clean", 5);
        if (config.native.cssstylesheet) {
          config.native.shadow.toggle.stylesheets({"disabled": true});
        }
      } catch (e) {
        if (config.log) {
          console.error(e);
        }
      }
    },
    "apply": function (e) {
      document.documentElement.removeAttribute(config.temporarily.id.start);
      /*  */
      const apply = config.custom.style && config.native.style;
      /*  */
      try {
        if (apply) {
          const loc = e.loc;
          const href_g = e.href_g;
          const href_c = e.href_c;
          const text_c = e.text_c;
          const text_n = e.text_n;
          const options = e.options;
          /*  */
          if (options.frameId === 0) {
            if (options.reload === false) {
              if (href_g === '' && href_c === '' && text_c === '' && text_n === '') {
                config.temporarily.remove(0, 1);
              } else {
                const action = options.temporarilyaction;
                const delay = options.temporarilydelay !== undefined ? Number(options.temporarilydelay) : 200;
                const attribute = options.temporarilybrightness ? config.temporarily.id.brightness : (options.temporarilydisplay ? config.temporarily.id.display : config.temporarily.id.simpledark);
                /*  */
                if (action) {
                  if (!options.recheck) {
                    config.temporarily.add(attribute);
                  }
                }
                /*  */
                if (text_n === '') {
                  config.temporarily.remove(delay, 2);
                }
              }
            } else {
              config.temporarily.remove(0, 3);
            }
          } else {
            config.temporarily.remove(0, 4);
          }
          /*  */
          config.check.darkmode.nodes(1);
          config.custom.style.textContent = text_c;
          config.native.style.textContent = text_n;
          /*  */
          href_c ? config.custom.link.setAttribute("href", href_c) : config.custom.link.removeAttribute("href");
          href_g ? config.general.link.setAttribute("href", href_g) : config.general.link.removeAttribute("href");
          /*  */
          if (text_n) {
            native.dark.observer.initiate(true);
            //
            native.dark.engine.is.active = true;
            config.native.sheet.disabled = false;
            document.documentElement.setAttribute(native.dark.attribute.theme, '');
            //
            if (config.native.cssstylesheet) {
              const src = chrome.runtime.getURL("data/content_script/page_context/inject.js");
              config.native.shadow.toggle.stylesheets({"disabled": false});
              native.dark.engine.process.cssstylesheet(src);
            }
            //
            native.dark.engine.analyze.document.sheets("process", 4);
          } else {
            if (native.dark.engine.is.active) {
              config.style.clear(options, 9);
            }
          }
        }
      } catch (e) {
        if (config.log) {
          console.error(e);
        }
      }
    }
  },
  "render": {
    "pre": function (e) {
      config.addon.state = e.state;
      /*  */
      const action = e.temporarilyaction;
      const parent = e.documentroot ? document.documentElement : document.head;
      /*  */
      if (config.addon.state === "dark") {
        if (action === true) {
          document.documentElement.setAttribute(config.temporarily.id.start, '');
        }
      }
      /*  */
      if (!config.general.link) {
        config.general.link = document.createElement("link");
        config.general.link.setAttribute("type", "text/css");
        config.general.link.setAttribute("rel", "stylesheet");
        config.general.link.setAttribute("id", "dark-mode-general-link");
      }
      /*  */
      if (!config.custom.link) {
        config.custom.link = document.createElement("link");
        config.custom.link.setAttribute("type", "text/css");
        config.custom.link.setAttribute("rel", "stylesheet");
        config.custom.link.setAttribute("id", "dark-mode-custom-link");
      }
      /*  */
      if (!config.custom.style) {
        config.custom.style = document.createElement("style");
        config.custom.style.setAttribute("lang", "en");
        config.custom.style.setAttribute("type", "text/css");
        config.custom.style.setAttribute("id", "dark-mode-custom-style");
      }
      /*  */
      if (!config.native.style) {
        config.native.style = document.createElement("style");
        config.native.style.setAttribute("lang", "en");
        config.native.style.setAttribute("type", "text/css");
        config.native.style.setAttribute("id", "dark-mode-native-style");
      }    
      /*  */
      if (!config.native.sheet) {
        config.native.sheet = document.createElement("style");
        config.native.sheet.setAttribute("lang", "en");
        config.native.sheet.setAttribute("type", "text/css");
        config.native.sheet.setAttribute("id", "dark-mode-native-sheet");
      }
      /*  */
      if (parent) {
        parent.appendChild(config.custom.link);
        parent.appendChild(config.general.link);
        parent.appendChild(config.custom.style);
        parent.appendChild(config.native.style);
        parent.appendChild(config.native.sheet);
        //
        config.native.stylesheet = config.native.sheet.sheet;
        background.send("load");
      } else {
        config.observer.head.observe(document, {
          "subtree": true,
          "childList": true,
        });
      }
    },
    "post": function (e) {
      try {
        config.addon.state = e.storage.state;
        /*  */
        if (config.addon.state === "dark") {
          config.colortemperature.remove();
          const page = e.top ? e.top : document.location.href;
          /*  */
          if (page.indexOf("/chrome/newtab") !== -1) {
            return config.style.clear(e, 1);
          }
          /*  */
          const darkness = config.check.darkness(e.storage);
          if (darkness) {
            config.native.darkness = darkness;
            return config.style.clear(e, 2);
          }
          /*  */
          const loaded = document.readyState === "complete";
          const darkcolor = loaded ? config.check.darkcolor.page(0) : false;
          if (darkcolor) {
            return config.style.remove(0);
          }
          /*  */
          const hostname = e.hostname ? e.hostname : config.hostname(page);
          if (e.storage.inclusiveaction) {
            const target = hostname ? hostname : page;
            if (e.storage.inclusivelist.indexOf(target) === -1) {
              if (e.storage.colortemperature) {
                config.colortemperature.render(e);
              }
              //
              return config.style.clear(e, 3);
            }
          }
          /*  */
          if (e.storage.whitelist) {
            for (let i = 0; i < e.storage.whitelist.length; i++) {
              const target = hostname ? hostname : page;
              if (e.storage.whitelist[i] === target) {
                return config.style.clear(e, 4);
              }
            }
          }
          /*  */
          website.theme.number.active = null;
          for (let i = 1; i <= website.total.themes.number; i++) {
            if (e.storage["dark_" + i]) {
              website.theme.number.active = i;
              break;
            }
          }
          /*  */
          config.native.selected = website.theme.number.active === website.theme.number.native;
          /*  */
          config.native.ignore = e.storage.nativeignore && config.native.selected;
          config.native.respect = e.storage.nativerespect && config.native.selected;
          config.native.compatible = e.storage.nativecompatible && config.native.selected;
          /*  */
          config.native.css.rules = e.storage.nativecssrules;
          config.native.css.variables = e.storage.nativecssvariables;
          /*  */
          config.native.remove.background.image = e.storage.nativeremoveimage;
          config.native.remove.background.color = e.storage.nativeremovecolor;
          /*  */
          config.native.temporarily.delay = e.storage.temporarilydelay;
          config.native.temporarily.action = e.storage.temporarilyaction;
          config.native.temporarily.display = e.storage.temporarilydisplay;
          config.native.temporarily.threshold = e.storage.temporarilythreshold;
          config.native.temporarily.simpledark = e.storage.temporarilysimpledark;
          config.native.temporarily.brightness = e.storage.temporarilybrightness;
          /*  */
          config.native.range.limit.min = e.storage.nativerangelimitmin;
          config.native.range.limit.max = e.storage.nativerangelimitmax;
          config.native.range.threshold.min = e.storage.nativerangethresholdmin;
          config.native.range.threshold.max = e.storage.nativerangethresholdmax;
          /*  */
          config.native.darken.background.shade = e.storage.nativedarkenshade;
          config.native.darken.background.image = e.storage.nativedarkenimage;
          config.native.darken.variable.gradient = e.storage.nativedarkenvariable;
          config.native.darken.background.gradient = e.storage.nativedarkengradient;
          /*  */
          config.native.force.color.font = e.storage.nativeforcefont;
          config.native.force.color.border = e.storage.nativeforceborder;
          config.native.force.color.svgfill = e.storage.nativeforcesvgfill;
          config.native.force.width.border = e.storage.nativeforceborderwidth;
          config.native.force.color.boxshadow = e.storage.nativeforceboxshadow;
          config.native.force.color.svgstroke = e.storage.nativeforcesvgstroke;
          config.native.force.color.textshadow = e.storage.nativeforcetextshadow;
          config.native.force.color.background = e.storage.nativeforcebackground;
          config.native.force.color.closetowhite = e.storage.nativeforceclosetowhite;
          config.native.force.color.transparency = e.storage.nativeforcetransparency;
          config.native.force.color.backgroundcolor = e.storage.nativeforcebackgroundcolor;
          config.native.force.color.closetowhitemin = e.storage.nativeforceclosetowhitemin;
          config.native.force.color.closetowhitemax = e.storage.nativeforceclosetowhitemax;
          config.native.force.color.closetowhitepercent = e.storage.nativeforceclosetowhitepercent;
          /*  */
          config.native.inline = e.storage.nativeinline;
          config.native.recheck = e.storage.nativerecheck;
          config.native.colorful = e.storage.nativecolorful;
          config.native.priority = e.storage.nativepriority;
          config.native.continue = e.storage.nativecontinue;
          config.native.supports = e.storage.nativesupports;
          config.native.deeprules = e.storage.nativedeeprules;
          config.native.documentroot = e.storage.documentroot;
          config.native.classname = e.storage.nativeclassname;
          config.native.keyframes = e.storage.nativekeyframes;
          config.native.mediaquery = e.storage.nativemediaquery;
          config.native.checkstylesheet = e.storage.checkstylesheet;
          config.native.mapcssvariables = e.storage.mapcssvariables;
          config.native.cssstylesheet = e.storage.nativecssstylesheet;
          config.native.rechecktimeout = e.storage.nativerechecktimeout;
          config.native.backgroundblend = e.storage.nativebackgroundblend;
          config.native.backgroundrelated = e.storage.nativebackgroundrelated;
          config.native.backgroundinitial = e.storage.nativebackgroundinitial;
          config.native.backgroundfallback = e.storage.nativebackgroundfallback;
          config.native.performanceobserver = e.storage.nativeperformanceobserver;
          config.native.backgroundtransparency = e.storage.nativebackgroundtransparency;
          /*  */
          config.native.best.pageload = e.storage.nativebestpageload;
          config.native.best.performance = e.storage.nativebestperformance;
          /*  */
          config.native.excludeiframes = e.storage.excludeiframes;
          config.native.excludeincolorschemedark = e.excludeincolorschemedark;
          config.native.excludecsscolorscheme = e.storage.excludecsscolorscheme;
          config.native.excludedarkbackground = e.storage.excludedarkbackground;
          config.native.excludedarkbackgroundnative = e.storage.excludedarkbackgroundnative;
          config.native.excludedarkbackgroundthreshold = e.storage.excludedarkbackgroundthreshold;
          /*  */
          config.native.colorfulmap = {
            "svg": e.storage["nativecolorful-svg"] !== undefined ? e.storage["nativecolorful-svg"] : false,
            "font": e.storage["nativecolorful-font"] !== undefined ? e.storage["nativecolorful-font"] : false,
            "border": e.storage["nativecolorful-border"] !== undefined ? e.storage["nativecolorful-border"] : false,
            "background": e.storage["nativecolorful-background"] !== undefined ? e.storage["nativecolorful-background"] : true
          };
          /*  */
          const uri = e.uri ? e.uri : decodeURIComponent(page);
          const options = {
            "reload": e.reload,
            "recheck": e.recheck,
            "frameId": e.frameId,
            "cssstylesheet": e.storage.nativecssstylesheet,
            "temporarilydelay": e.storage.temporarilydelay,
            "temporarilyaction": e.storage.temporarilyaction,
            "temporarilydisplay": e.storage.temporarilydisplay,
            "temporarilythreshold": e.storage.temporarilythreshold,
            "temporarilysimpledark": e.storage.temporarilysimpledark,
            "temporarilybrightness": e.storage.temporarilybrightness
          };
          /*  */
          for (let name in website.custom.regex.rules) {
            const cond_1 = config.native.ignore === false;
            const cond_2 = config.native.compatible === false;
            const cond_3 = config.native.compatible && e.compatible.indexOf(name) === -1;
            /*  */
            let usecustom = cond_1 && (cond_2 || cond_3);
            if (usecustom) {
              if (e.storage[name]) {
                let rule = new RegExp(website.custom.regex.rules[name]);
                if (rule.test(uri)) {
                  let href_g = config.addon.state === "dark" ? chrome.runtime.getURL("data/content_script/custom/dark.css") : '';
                  let href_c = config.addon.state === "dark" ? chrome.runtime.getURL("data/content_script/custom/" + name + ".css") : '';
                  /*  */
                  href_g = website.exclude.from.custom.dark.mode.indexOf(name) === -1 ? href_g : '';
                  config.style.apply({"loc": 1, "href_g": href_g, "href_c": href_c, "text_c": '', "text_n": '', "options": options});
                  return;
                }
              }
            }
          }
          /*  */
          if (website.theme.number.active) {
            if (website.theme.number.active === website.theme.number.custom) {
              config.style.apply({"loc": 2, "href_g": '', "href_c": '', "text_c": e.storage.custom, "text_n": '', "options": options});
            } else if (config.native.selected) {
              const rules = config.native.css.rules;
              const variables = JSON.stringify(config.native.css.variables, null, 2).replace(/\"/g, '').replace(/\,\n/g, ";\n");
              const nativecss = ":root, ::after, ::before, ::backdrop " + variables + "\n\n" + rules;
              //
              config.style.apply({"loc": 3, "href_g": '', "href_c": '', "text_c": '', "text_n": nativecss, "options": options});
            } else {
              let href_g = chrome.runtime.getURL("data/content_script/general/dark_" + website.theme.number.active + ".css");
              config.style.apply({"loc": 4, "href_g": href_g, "href_c": '', "text_c": '', "text_n": '', "options": options});
            }
          } else {
            config.style.clear(e, 5);
          }
          /*  */
          if (config.native.excludeiframes) {
            if (e.frameId !== 0) {
              window.top.postMessage({
                "frameId": e.frameId,
                "from": "native-dark-context-iframe-for-exclude"
              }, '*');
            }
          }
        } else {
          if (e.storage.colortemperature) {
            config.colortemperature.render(e);
          }
          /*  */
          config.style.clear(e, 6);
        }
      } catch (e) {
        if (config.log) {
          console.error(e);
        }
      }
    }
  },
  "native": {
    "inline": false,
    "ignore": false,
    "recheck": true,
    "respect": false,
    "colorful": true,
    "continue": false,
    "selected": false,
    "priority": false,
    "colorfulmap": {},
    "darkness": false,
    "classname": false,
    "compatible": true,
    "stylesheet": null,
    "keyframes": false,
    "mediaquery": false,
    "darknessstorage": {},
    "documentroot": false,
    "cssstylesheet": false,
    "excludeiframes": false,
    "checkstylesheet": true,
    "mapcssvariables": true,
    "backgroundblend": true,
    "backgroundfallback": true,
    "performanceobserver": false,
    "backgroundtransparency": 10,
    "excludecsscolorscheme": true,
    "excludedarkbackground": true,
    "excludemetacolorscheme": true,
    "excludedarkbackgroundnative": false,
    "excludedarkbackgroundthreshold": 128,
    "style": document.getElementById("dark-mode-native-style"),
    "sheet": document.getElementById("dark-mode-native-sheet"),
    "css": {
      "rules": '',
      "variables": ''
    },
    "best": {
      "pageload": false,
      "performance": true
    },
    "remove": {
      "background": {
        "image": true
      }
    },
    "temporarily": {
      "delay": 200,
      "action": true,
      "display": true,
      "threshold": 1000,
      "brightness": false
    },
    "darken": {
      "variable": {
        "gradient": false
      },
      "background": {
        "image": true,
        "gradient": true,
        "shade": "linear-gradient(hsla(0, 0%, 0%, 0.85), hsla(0, 0%, 0%, 0.75))"
      }
    },
    "range": {
      "limit": {
        "min": 10,
        "max": 90
      },
      "threshold": {
        "min": 10,
        "max": 10
      }
    },
    "force": {
      "width": {
        "border": false
      },
      "color": {
        "font": true,
        "border": true,
        "svgfill": true,
        "svgstroke": true,
        "boxshadow": true,
        "textshadow": true,
        "background": false,
        "transparency": true,
        "backgroundcolor": true,
      }
    },
    "shadow": {
      "sheets": [],
      "timeout": null,
      "classnames": [],
      "toggle": {
        "stylesheets": function (e) {
          if (native.dark.engine.map.css.stylesheets) {
            for (let key in native.dark.engine.map.css.stylesheets) {
              const cssstylesheet = native.dark.engine.map.css.stylesheets[key];
              if (cssstylesheet) {
                cssstylesheet.disabled = e.disabled;
                //
                const shadownode = cssstylesheet[native.dark.object.shadownode];
                if (shadownode) {
                  if (e.disabled) {
                    shadownode.removeAttribute(native.dark.attribute.theme);
                  } else {
                    shadownode.setAttribute(native.dark.attribute.theme, '');
                  }
                }
              }
            }
          }
        }
      },
      "find": {
        "nodes": function (target, selector) {
          const nodes = [];
          //
          try {
            const recursivefind = function (node) {
              if (node) {
                if (node.nodeType !== Node.ELEMENT_NODE) return;
                if (node.matches(selector)) nodes.push(node);
                //
                const nodechilds = node.children;
                if (nodechilds) {
                  if (nodechilds.length) {
                    for (const nodechild of nodechilds) {
                      recursivefind(nodechild);
                    }
                  }
                }
                //
                const shadowoot = node.shadowRoot;
                if (shadowoot) {
                  const shadowchilds = shadowoot.children;
                  if (shadowchilds) {
                    for (const shadowchild of shadowchilds) {
                      recursivefind(shadowchild);
                    }
                  }
                }
              }
            }
            //
            recursivefind(target);
          } catch (e) {
            if (config.log) {
              console.error(e);
            }
          }
          //
          return nodes;
        },
        "stylesheets": function (target) {
          try {
            const selector = '[' + native.dark.class.shadownode + ']';
            const shadownodes = config.native.shadow.find.nodes(target, selector);
            //
            if (shadownodes) {
              if (shadownodes.length) {
                for (let i = 0; i < shadownodes.length; i++) {
                  let shadow = {};
                  //
                  shadow.node = shadownodes[i];
                  shadow.classname = shadow.node.getAttribute(native.dark.class.shadownode);
                  shadow.action = config.native.shadow.classnames.indexOf(shadow.classname) === -1;
                  //
                  if (shadow.action) {
                    shadow.root = shadow.node.shadowRoot;
                    //
                    if (shadow.root) {
                      config.native.shadow.classnames.push(shadow.classname);
                      //
                      shadow.stylesheets = [...shadow.root.styleSheets];
                      shadow.adoptedstylesheets = [...shadow.root.adoptedStyleSheets];
                      shadow.sheets = [...shadow.stylesheets, ...shadow.adoptedstylesheets];
                      //
                      let cssstylesheet = native.dark.engine.map.css.stylesheets[shadow.classname];
                      if (cssstylesheet === undefined) {
                        cssstylesheet = new CSSStyleSheet();
                        cssstylesheet[native.dark.object.shadownode] = shadow.node;
                        cssstylesheet.disabled = native.dark.engine.is.active ? false : true;
                        native.dark.engine.map.css.stylesheets[shadow.classname] = cssstylesheet;
                      }
                      //
                      if (shadow.sheets) {
                        if (shadow.sheets.length) {
                          for (let j = 0; j < shadow.sheets.length; j++) {
                            let sheet = shadow.sheets[j];
                            //
                            if (sheet[native.dark.object.shadownode] === undefined) {
                              sheet[native.dark.attribute.shadowroot] = true;
                              //
                              let _cssstylesheet = sheet[native.dark.object.cssstylesheet];
                              if (_cssstylesheet === undefined) {
                                sheet[native.dark.object.cssstylesheet] = cssstylesheet;
                                shadow.root.adoptedStyleSheets = [...shadow.root.adoptedStyleSheets, cssstylesheet];
                              } else {
                                shadow.root.adoptedStyleSheets = [...shadow.root.adoptedStyleSheets, _cssstylesheet];
                              }
                            }
                          }
                          //
                          config.native.shadow.sheets = [...config.native.shadow.sheets, ...shadow.sheets];
                        }
                      }
                    }
                  }
                }
              }
            }
          } catch (e) {
            if (config.log) {
              console.error(e);
            }
          }
        }
      }
    }
  }
};

config.start();

background.receive("content", config.content);
background.receive("storage", config.render.post);

window.addEventListener("load", config.load, false);
window.addEventListener("message", config.message, false);
