var core = {
  "start": function () {
    core.load();
  },
  "install": function () {
    core.load();
    core.update.storage();
  },
  "load": function () {
    core.update.alarm();
    core.update.contextmenu();
  },
  "alarm": {
    "reset": function () {
      app.alarms.reset();
    },
    "create": {
      "on": function () {
        app.storage.get("scheduleon", function (e) {
          if (e.scheduleon && e.scheduleon !== undefined) {
            const date = new Date();
            const H = e.scheduleon.split(':')[0];
            const M = e.scheduleon.split(':')[1];
            /*  */
            let diff = new Date(date.getFullYear(), date.getMonth(), date.getDate(), Number(H), Number(M), 0, 0) - date;
            if (diff < 0) diff += 86400000; // next day
            /*  */
            app.alarms.clear("dark-mode-on", function () {
              app.alarms.create("dark-mode-on", {
                "when": Date.now() + diff
              });
            });
          }
        });
      },
      "off": function () {
        app.storage.get("scheduleoff", function (e) {
          if (e.scheduleoff && e.scheduleoff !== undefined) {
            const date = new Date();
            const H = e.scheduleoff.split(':')[0];
            const M = e.scheduleoff.split(':')[1];
            /*  */
            let diff = new Date(date.getFullYear(), date.getMonth(), date.getDate(), Number(H), Number(M), 0, 0) - date;
            if (diff < 0) diff += 86400000; // next day
            /*  */
            app.alarms.clear("dark-mode-off", function () {
              app.alarms.create("dark-mode-off", {
                "when": Date.now() + diff
              });
            });
          }
        });
      }
    }
  },
  "action": {
    "reload": function (e) {
      app.storage.update(function () {
        core.update.page(e, true, false);
      });
    },
    "alarm": function (e) {
      if (e) {
        if (e.name) {
          config.addon.state = e.name === "dark-mode-on" ? "dark" : "light";
          core.update.alarm();
        }
      }
    },
    "storage": function (changes) {
      if ("toggleaction" in changes) {
        core.update.button(null);
      }
      /*  */
      if ("scheduleon" in changes || "scheduleoff" in changes || "scheduleaction" in changes) {
        core.update.alarm();
      }
      /*  */
      if ("state" in changes || "inclusiveaction" in changes || "colortemperature" in changes) {
        core.update.button(null);
        core.update.contextmenu();
      }
    },
    "fetch": function (e) {
      if (e.href) {
        fetch(e.href, {"cache": "default"}).then(r => r.text()).then(function (content) {
          if (content) {
            app.page.send("content", {
              "href": e.href,
              "index": e.index,
              "content": content
            }, e ? e.tabId : null, e ? e.frameId : null);
          }
        }).catch(e => {
          //console.error(e);
        });
      }
    },
    "contextmenu": function (e) {
      if (e) {
        const pageUrl = e.pageUrl;
        /*  */
        if (e.menuItemId === "dark-mode-contextmenu-exclude") {
          app.storage.get({"whitelist": []}, function (data) {
            let whitelist = data.whitelist;
            let hostname = config.hostname(pageUrl);
            whitelist.push(hostname ? hostname : pageUrl);
            whitelist = whitelist.filter(function (element, index, array) {return element && array.indexOf(element) === index});
            app.storage.set({"whitelist": whitelist});
          });
        }
        /*  */
        if (e.menuItemId === "dark-mode-contextmenu-include") {
          app.storage.get({"inclusivelist": []}, function (data) {
            let inclusivelist = data.inclusivelist;
            let hostname = config.hostname(pageUrl);
            inclusivelist.push(hostname ? hostname : pageUrl);
            inclusivelist = inclusivelist.filter(function (element, index, array) {return element && array.indexOf(element) === index});
            app.storage.set({"inclusivelist": inclusivelist}, function () {
              core.update.button({"url": pageUrl});
            });
          });
        }
        /*  */
        if (e.menuItemId === "color-temperature-contextmenu-exclude") {
          app.storage.get({"colortemperature-whitelist": []}, function (data) {
            let whitelist = data["colortemperature-whitelist"];
            let hostname = config.hostname(pageUrl);
            whitelist.push(hostname ? hostname : pageUrl);
            whitelist = whitelist.filter(function (element, index, array) {return element && array.indexOf(element) === index});
            app.storage.set({"colortemperature-whitelist": whitelist}, function () {
              core.update.button({"url": pageUrl});
            });
          });
        }
      }
    },
    "button": function (tab) {
      app.storage.get(null, function (e) {
        if (e.inclusiveaction && e.toggleaction) {
          let inclusivelist = e.inclusivelist;
          /*  */
          if (tab) {
            if (tab.url) {
              const hostname = config.hostname(tab.url);
              const domain = hostname ? hostname : tab.url;
              const index = inclusivelist.indexOf(domain);
              /*  */
              if (index !== -1) {
                inclusivelist.splice(index, 1);
              } else {
                inclusivelist.push(domain);
                inclusivelist = inclusivelist.filter(function (element, index, array) {return element && array.indexOf(element) === index});
              }
              /*  */
              app.storage.set({"inclusivelist": inclusivelist}, function () {
                core.update.button(tab);
              });
            }
          }
        } else {
          config.addon.state = config.addon.state === "dark" ? "light" : "dark";
        }
      });
    }
  },
  "update": {
    "page": function (e, reload, recheck) {
      app.page.send("storage", {
        "reload": reload,
        "recheck": recheck,
        "top": e ? e.top : null,
        "uri": e ? e.uri : null,
        "storage": app.storage.local,
        "frameId": e ? e.frameId : null,
        "hostname": e ? e.hostname : null,
        "compatible": website.custom.compatible
      }, e ? e.tabId : null, e ? e.frameId : null);
    },
    "alarm": function () {
      app.storage.get("scheduleaction", function (e) {
        if (e.scheduleaction !== undefined) {
          if (e.scheduleaction === true) {
            core.alarm.create.on();
            core.alarm.create.off();
          } else {
            core.alarm.reset();
          }
        }
      });
    },
    "contextmenu": function () {
      app.storage.get(null, function (e) {
        app.contextmenu.clear(function () {
          if (e.state === "dark") {
            if (e.inclusiveaction) {
              app.contextmenu.create({
                "contexts": ["page"],
                "title": "Include in dark mode",
                "id": "dark-mode-contextmenu-include"
              }, app.error);
            } else {
              app.contextmenu.create({
                "contexts": ["page"],
                "title": "Exclude from dark mode",
                "id": "dark-mode-contextmenu-exclude"
              }, app.error);
            }
          } else {
            if (e.colortemperature) {
              app.contextmenu.create({
                "contexts": ["page"],
                "title": "Exclude from color temperature",
                "id": "color-temperature-contextmenu-exclude"
              }, app.error);
            } else {
              app.contextmenu.create({
                "contexts": ["page"],
                "title": "Exclude from dark mode",
                "id": "dark-mode-contextmenu-exclude"
              }, app.error);
            }
          }
        });
      });
    },
    "button": function (tab) {
      let options = null;
      let state = config.addon.state;
      /*  */
      if (tab) {
        if (tab.url) {
          const hostname = config.hostname(tab.url);
          options = {
            "url": hostname ? (hostname.indexOf(':') !== -1 ? tab.url : "*://*." + hostname + "/*") : tab.url
          }
        }
      }
      /*  */
      app.storage.get(null, function (e) {
        app.tab.query.all(options, function (tabs) {
          if (tabs) {
            if (tabs.length) {
              for (let i = 0; i < tabs.length; i++) {
                if (tabs[i]) {
                  if (tabs[i].url) {
                    if (e.inclusiveaction && e.toggleaction) {
                      const inclusivelist = e.inclusivelist;
                      const hostname = config.hostname(tabs[i].url);
                      const domain = hostname ? hostname : tabs[i].url;
                      const index = inclusivelist.indexOf(domain);
                      state = index !== -1 ? "dark" : "light";
                    } else {
                      state = config.addon.state;
                    }
                  } else {
                    state = config.addon.state;
                  }
                  /*  */
                  app.button.icon(tabs[i].id, state);
                  app.button.title(tabs[i].id, "Current State: " + state.toUpperCase());
                }
              }
            }
          }
        });
      });
    },
    "storage": function () {
      app.storage.get(null, function (data) {
        let tmp = {};
        let cssrules = {};
        const active = "dark_" + 41;
        const cssvariables = website.custom.native.css.variables;
        /*  */
        cssrules.old = data.native;
        cssrules.new = website.custom.native.css.rules.replace(/\n/, '').replace(/          /g, '');
        /*  */
        tmp["custom"] = data.custom !== undefined ? data.custom : '';
        tmp["state"] = data.state !== undefined ? data.state : "light";
        tmp["fontsize"] = data.fontsize !== undefined ? data.fontsize : 13;
        tmp["whitelist"] = data.whitelist !== undefined ? data.whitelist : [];
        tmp["opensupport"] = data.opensupport !== undefined ? data.opensupport : true;
        tmp["cookie"] = data.cookie !== undefined ? data.cookie : config.exception.keys;
        tmp["excludeclassnames"] = data.excludeclassnames !== undefined ? data.excludeclassnames : config.exception.classnames;
        tmp["excludeattributes"] = data.excludeattributes !== undefined ? data.excludeattributes : config.exception.attributes;
        /*  */
        tmp["inclusivelist"] = data.inclusivelist !== undefined ? data.inclusivelist : [];
        tmp["toggleaction"] = data.toggleaction !== undefined ? data.toggleaction : false;
        tmp["inclusiveaction"] = data.inclusiveaction !== undefined ? data.inclusiveaction : false;
        /*  */
        tmp["scheduleon"] = data.scheduleon !== undefined ? data.scheduleon : '';
        tmp["scheduleoff"] = data.scheduleoff !== undefined ? data.scheduleoff : '';
        tmp["scheduleaction"] = data.scheduleaction !== undefined ? data.scheduleaction : false;
        /*  */
        tmp["temporarilydelay"] = data.temporarilydelay !== undefined ? data.temporarilydelay : 200;
        tmp["temporarilyaction"] = data.temporarilyaction !== undefined ? data.temporarilyaction : true;
        tmp["temporarilydisplay"] = data.temporarilydisplay !== undefined ? data.temporarilydisplay : false;
        tmp["temporarilythreshold"] = data.temporarilythreshold !== undefined ? data.temporarilythreshold : 1000;
        tmp["temporarilysimpledark"] = data.temporarilysimpledark !== undefined ? data.temporarilysimpledark : true;
        tmp["temporarilybrightness"] = data.temporarilybrightness !== undefined ? data.temporarilybrightness : false;
        /*  */
        tmp["documentroot"] = data.documentroot !== undefined ? data.documentroot : false;
        tmp["nativeinline"] = data.nativeinline !== undefined ? data.nativeinline : false;
        tmp["nativeignore"] = data.nativeignore !== undefined ? data.nativeignore : false;
        tmp["nativerecheck"] = data.nativerecheck !== undefined ? data.nativerecheck : true;
        tmp["nativerespect"] = data.nativerespect !== undefined ? data.nativerespect : false;
        tmp["nativepriority"] = data.nativepriority !== undefined ? data.nativepriority : false;
        tmp["nativecontinue"] = data.nativecontinue !== undefined ? data.nativecontinue : false;
        tmp["nativesupports"] = data.nativesupports !== undefined ? data.nativesupports : false;
        tmp["checkstylesheet"] = data.checkstylesheet !== undefined ? data.checkstylesheet : true;
        tmp["mapcssvariables"] = data.mapcssvariables !== undefined ? data.mapcssvariables : true;
        tmp["nativekeyframes"] = data.nativekeyframes !== undefined ? data.nativekeyframes : false;
        tmp["nativeclassname"] = data.nativeclassname !== undefined ? data.nativeclassname : false;
        tmp["nativedeeprules"] = data.nativedeeprules !== undefined ? data.nativedeeprules : false;
        tmp["nativecompatible"] = data.nativecompatible !== undefined ? data.nativecompatible : true;
        tmp["nativemediaquery"] = data.nativemediaquery !== undefined ? data.nativemediaquery : false;
        tmp["nativeremoveimage"] = data.nativeremoveimage !== undefined ? data.nativeremoveimage : true;
        tmp["nativeremovecolor"] = data.nativeremovecolor !== undefined ? data.nativeremovecolor : false;
        tmp["nativebestpageload"] = data.nativebestpageload !== undefined ? data.nativebestpageload : false;
        tmp["nativerechecktimeout"] = data.nativerechecktimeout !== undefined ? data.nativerechecktimeout : 0;
        tmp["nativebackgroundblend"] = data.nativebackgroundblend !== undefined ? data.nativebackgroundblend : true;
        tmp["nativebestperformance"] = data.nativebestperformance !== undefined ? data.nativebestperformance : true;
        tmp["nativebackgroundinitial"] = data.nativebackgroundinitial !== undefined ? data.nativebackgroundinitial : true;
        tmp["nativebackgroundrelated"] = data.nativebackgroundrelated !== undefined ? data.nativebackgroundrelated : true;
        tmp["nativebackgroundfallback"] = data.nativebackgroundfallback !== undefined ? data.nativebackgroundfallback : true;
        tmp["nativeperformanceobserver"] = data.nativeperformanceobserver !== undefined ? data.nativeperformanceobserver : false;
        tmp["nativebackgroundtransparency"] = data.nativebackgroundtransparency !== undefined ? data.nativebackgroundtransparency : 10;
        /*  */
        tmp["nativecssstylesheet"] = data.nativecssstylesheet !== undefined ? data.nativecssstylesheet : false;
        tmp["nativecssvariables"] = data.nativecssvariables !== undefined ? data.nativecssvariables : cssvariables;
        tmp["nativecssrules"] = data.nativecssrules !== undefined ? data.nativecssrules : (cssrules.old !== undefined ? cssrules.old : cssrules.new);
        /*  */
        tmp["nativedarkenimage"] = data.nativedarkenimage !== undefined ? data.nativedarkenimage : true;
        tmp["nativedarkengradient"] = data.nativedarkengradient !== undefined ? data.nativedarkengradient : true;
        tmp["nativedarkenvariable"] = data.nativedarkenvariable !== undefined ? data.nativedarkenvariable : false;
        tmp["nativedarkenshade"] = data.nativedarkenshade !== undefined ? data.nativedarkenshade : "linear-gradient(hsla(0, 0%, 0%, 0.85), hsla(0, 0%, 0%, 0.75))";
        /*  */
        tmp["nativerangelimitmin"] = data.nativerangelimitmin !== undefined ? data.nativerangelimitmin : 10;
        tmp["nativerangelimitmax"] = data.nativerangelimitmax !== undefined ? data.nativerangelimitmax : 90;
        tmp["nativerangethresholdmin"] = data.nativerangethresholdmin !== undefined ? data.nativerangethresholdmin : 10;
        tmp["nativerangethresholdmax"] = data.nativerangethresholdmax !== undefined ? data.nativerangethresholdmax : 75;
        /*  */
        tmp["nativecolorful"] = data.nativecolorful !== undefined ? data.nativecolorful : true;
        tmp["nativecolorful-svg"] = data["nativecolorful-svg"] !== undefined ? data["nativecolorful-svg"] : false;
        tmp["nativecolorful-font"] = data["nativecolorful-font"] !== undefined ? data["nativecolorful-font"] : false;
        tmp["nativecolorful-border"] = data["nativecolorful-border"] !== undefined ? data["nativecolorful-border"] : false;
        tmp["nativecolorful-background"] = data["nativecolorful-background"] !== undefined ? data["nativecolorful-background"] : true;
        /*  */
        tmp["nativeforcefont"] = data.nativeforcefont !== undefined ? data.nativeforcefont : true;
        tmp["nativeforceborder"] = data.nativeforceborder !== undefined ? data.nativeforceborder : true;
        tmp["nativeforcesvgfill"] = data.nativeforcesvgfill !== undefined ? data.nativeforcesvgfill : true;
        tmp["nativeforcesvgstroke"] = data.nativeforcesvgstroke !== undefined ? data.nativeforcesvgstroke : true;
        tmp["nativeforceboxshadow"] = data.nativeforceboxshadow !== undefined ? data.nativeforceboxshadow : true;
        tmp["nativeforcetextshadow"] = data.nativeforcetextshadow !== undefined ? data.nativeforcetextshadow : true;
        tmp["nativeforcebackground"] = data.nativeforcebackground !== undefined ? data.nativeforcebackground : true;
        tmp["nativeforceborderwidth"] = data.nativeforceborderwidth !== undefined ? data.nativeforceborderwidth : false;
        tmp["nativeforcetransparency"] = data.nativeforcetransparency !== undefined ? data.nativeforcetransparency : true;
        tmp["nativeforceclosetowhite"] = data.nativeforceclosetowhite !== undefined ? data.nativeforceclosetowhite : true;
        tmp["nativeforceclosetowhitemin"] = data.nativeforceclosetowhitemin !== undefined ? data.nativeforceclosetowhitemin : 5;
        tmp["nativeforceclosetowhitemax"] = data.nativeforceclosetowhitemax !== undefined ? data.nativeforceclosetowhitemax : 95;
        tmp["nativeforcebackgroundcolor"] = data.nativeforcebackgroundcolor !== undefined ? data.nativeforcebackgroundcolor : true;
        tmp["nativeforceclosetowhitepercent"] = data.nativeforceclosetowhitepercent !== undefined ? data.nativeforceclosetowhitepercent : 10;
        /*  */
        tmp["excludeiframes"] = data.excludeiframes !== undefined ? data.excludeiframes : false;
        tmp["excludecsscolorscheme"] = data.excludecsscolorscheme !== undefined ? data.excludecsscolorscheme : true;
        tmp["excludedarkbackground"] = data.excludedarkbackground !== undefined ? data.excludedarkbackground : true;
        tmp["excludemetacolorscheme"] = data.excludemetacolorscheme !== undefined ? data.excludemetacolorscheme : true;
        tmp["excludeincolorschemedark"] = data.excludeincolorschemedark !== undefined ? data.excludeincolorschemedark : true;
        tmp["excludedarkbackgroundnative"] = data.excludedarkbackgroundnative !== undefined ? data.excludedarkbackgroundnative : false;
        tmp["excludedarkbackgroundthreshold"] = data.excludedarkbackgroundthreshold !== undefined ? data.excludedarkbackgroundthreshold : 128;
        /*  */
        tmp["colortemperature"] = data.colortemperature !== undefined ? data.colortemperature : false;
        tmp["colortemperature-red"] = data["colortemperature-red"] !== undefined ? data["colortemperature-red"] : 255;
        tmp["colortemperature-blue"] = data["colortemperature-blue"] !== undefined ? data["colortemperature-blue"] : 199;
        tmp["colortemperature-green"] = data["colortemperature-green"] !== undefined ? data["colortemperature-green"] : 227;
        tmp["colortemperature-opacity"] = data["colortemperature-opacity"] !== undefined ? data["colortemperature-opacity"] : 100;
        tmp["colortemperature-whitelist"] = data["colortemperature-whitelist"] !== undefined ? data["colortemperature-whitelist"] : [];
        /*  */
        tmp["section-1"] = data["section-1"] !== undefined ? data["section-1"] : false;
        tmp["section-2"] = data["section-2"] !== undefined ? data["section-2"] : false;
        tmp["section-3"] = data["section-3"] !== undefined ? data["section-3"] : false;
        tmp["section-4"] = data["section-4"] !== undefined ? data["section-4"] : true;
        tmp["section-5"] = data["section-5"] !== undefined ? data["section-5"] : false;
        tmp["section-6"] = data["section-6"] !== undefined ? data["section-6"] : false;
        tmp["section-7"] = data["section-7"] !== undefined ? data["section-7"] : false;
        /*  */
        for (let i = 1; i <= website.total.themes.number; i++) tmp["dark_" + i] = data["dark_" + i] !== undefined ? data["dark_" + i] : false;
        for (let name in website.custom.regex.rules) tmp[name] = data[name] !== undefined ? data[name] : true;
        tmp[active] = data[active] !== undefined ? data[active] : true;
        /*  */
        app.storage.set(tmp);
      });
    }
  }
};

app.storage.load(core.update.button);

app.tab.on.updated(core.update.button);
app.button.on.clicked(core.action.button);
app.contextmenu.on.clicked(core.action.contextmenu);

app.page.receive("fetch", core.action.fetch);
app.page.receive("reload", core.action.reload);
app.page.receive("load", function (e) {core.update.page(e, false, false)});
app.page.receive("recheck", function (e) {core.update.page(e, false, true)});

app.options.receive("toggle-dark", function () {config.addon.state = "dark"});
app.options.receive("dark-mode-item", function () {app.tab.open(app.homepage())});
app.options.receive("test-dark-mode", function () {app.tab.open(config.page.test)});
app.options.receive("open-support-page", function () {app.tab.open(app.homepage())});
app.options.receive("dark-theme-item", function () {app.tab.open(config.page.theme)});
app.options.receive("reset-addon", function () {app.storage.clear(core.update.storage)});
app.options.receive("dark-new-tab-item", function () {app.tab.open(config.page.newtab)});
app.options.receive("youtube-tutorial", function () {app.tab.open(config.page.tutorial)});
app.options.receive("make-a-donation", function () {app.tab.open(app.homepage() + "?reason=support")});

app.on.startup(core.start);
app.on.installed(core.install);
app.on.alarm(core.action.alarm);
app.on.storage(core.action.storage);
