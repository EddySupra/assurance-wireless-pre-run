var native = {
  "dark": {
    "object": {
      "shadownode": "native-dark-object-shadownode",
      "cssstylesheet": "native-dark-object-cssstylesheet"
    },
    "attribute": {
      "theme": "native-dark-active",
      "processed": "native-dark-attribute-processed",
      "shadowroot": "native-dark-attribute-shadowroot"
    },
    "class": {
      "cloned": "native-dark-class-cloned",
      "modified": "native-dark-class-modified",
      "original": "native-dark-class-original",
      "processed": "native-dark-class-processed",
      "shadownode": "native-dark-class-shadownode"
    },
    "regexp": {
      "url": /url\(['"]?((?:\S*?\(\S*?\))*\S*?)['"]?\)/,
      "check": /(?:-|_)(\d+[\/\d. ]*|\d)x|(\d+[\/\d. ]*|\d)x(?:-|_)/,
      "relative": /url\((?!['"]?(?:data:|https?:|\/\/))(['"]?)([^'")]*)\1\)/g,
      "color": new RegExp(`(#(?:[0-9a-f]{2}){2,4}|(#[0-9a-f]{3})|(rgb|hsl)a?\\((-?\\d+%?[,\\s]+){2,3}\\s*[\\d\\.]+%?\\)|${website.color.names.join('|')})`, 'i')
    },
    "theme": {
      "number": 41,
      "css": {
        "base": {
          "url": "native-dark-base-url"
        },
        "variable": {
          "prefix": "--native-dark-"
        }
      }
    },
    "observer": {
      "map": {},
      "delay": 0,
      "timeout": {
        'a': null, 
        'b': null, 
        'c': null,
        'd': null,
        'e': null,
        'f': null,
        'g': null,
        'h': null,
        'i': null,
        'j': null
      },
      "initiate": function (flag) {
        if (flag) {
          if (PerformanceObserver) {
            if (config.native.performanceobserver) {
              if (!native.dark.observer.performance.short.mutation) {
                native.dark.observer.performance.short.mutation = new PerformanceObserver(native.dark.observer.performance.short.callback);
                native.dark.observer.performance.short.mutation.observe({"entryTypes": native.dark.observer.performance.short.options});
              }
              //
              if (window.PerformanceLongTaskTiming !== undefined) {
                if (!native.dark.observer.performance.long.mutation) {
                  native.dark.observer.performance.long.mutation = new PerformanceObserver(native.dark.observer.performance.long.callback);
                  native.dark.observer.performance.long.mutation.observe({"entryTypes": native.dark.observer.performance.long.options});
                }
              }
            }
          }
          //
          if (MutationObserver) {
            if (!native.dark.observer.element.mutation) {
              native.dark.observer.element.mutation = new MutationObserver(native.dark.observer.element.callback);
              native.dark.observer.element.mutation.observe(document.documentElement, native.dark.observer.element.options);
            }
            //
            if (config.native.inline) {
              if (!native.dark.observer.style.mutation) {
                native.dark.observer.style.mutation = new MutationObserver(native.dark.observer.style.callback);
                native.dark.observer.style.mutation.observe(document.documentElement, native.dark.observer.style.options);
              }
            }
            //
            if (config.native.classname) {
              if (!native.dark.observer.classname.mutation) {
                native.dark.observer.classname.mutation = new MutationObserver(native.dark.observer.classname.callback);
                native.dark.observer.classname.mutation.observe(document.documentElement, native.dark.observer.classname.options);
              }
            }
          }
        } else {
          if (MutationObserver) {
            if (!native.dark.observer.element.mutation) {
              native.dark.observer.element.mutation = new MutationObserver(native.dark.observer.element.callback);
              native.dark.observer.element.mutation.observe(document.documentElement, native.dark.observer.element.options);
            }
          }
        }
      },
      "classname": {
        "mutation": null,
        "options": {
          "subtree": true,
          "attributes" : true,
          "attributeFilter": ["class"]
        },
        "callback": function (mutations) {
          if (mutations) {
            try {
              for (let mutation of mutations) {
                if (mutation.attributeName) {
                  if (mutation.attributeName === "class") {
                    const node = mutation.target;
                    //
                    if (node) {
                      if (node.nodeType === Node.ELEMENT_NODE) {
                        if (native.dark.observer.timeout.e) window.clearTimeout(native.dark.observer.timeout.e);
                        native.dark.observer.timeout.e = window.setTimeout(function () {
                          if (config.log) console.error("process", htmlname);
                          native.dark.engine.analyze.document.sheets("process", 6);
                        }, native.dark.observer.delay);
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
      },
      "performance": {
        "short": {
          "mutation": null,
          "options": [
            "paint",
            "layout-shift"
          ],
          "callback": function (e) {
            if (config.native.best.pageload) {
              if (native.dark.observer.timeout.f) window.clearTimeout(native.dark.observer.timeout.f);
              native.dark.observer.timeout.f = window.setTimeout(function () {
                if (config.log) console.error("process", e);
                //
                native.dark.observer.root.stylemap(1);
                native.dark.observer.root.attributes(1);
                //
                native.dark.engine.analyze.document.sheets("process", 7);
              }, native.dark.observer.delay);
            }
          }
        },
        "long": {
          "delay": 300,
          "mutation": null,
          "options": [
            "longtask"
          ],
          "callback": function (e) {
            if (config.native.best.pageload) {
              if (document.visibilityState === "hidden") {
                if (native.dark.observer.timeout.h) window.clearTimeout(native.dark.observer.timeout.h);
                native.dark.observer.timeout.h = window.setTimeout(function () {
                  if (config.log) console.error("process", e);
                  //
                  native.dark.observer.root.stylemap(2);
                  native.dark.observer.root.attributes(2);
                  //
                  native.dark.engine.analyze.document.sheets("process", 8);
                }, native.dark.observer.delay + native.dark.observer.performance.long.delay);
              }
            }
            //
            if (config.temporarily.is.removed === false) {
              if (native.dark.observer.timeout.h) window.clearTimeout(native.dark.observer.timeout.h);
              native.dark.observer.timeout.h = window.setTimeout(function () {
                if (e) {
                  const entries = e.getEntries();
                  const name = entries && entries.length ? entries[0].name : '';
                  if (name === "self") {
                    const delay = config.native.temporarily.delay !== undefined ? Number(config.native.temporarily.delay) : 200;
                    //
                    config.temporarily.is.removed = true;
                    config.temporarily.remove(delay, 6);
                  }
                }
              }, native.dark.observer.delay);
            }
          }
        }
      },
      "root": {
        "stylemap": function (loc) {
          if (config.log) console.error("stylemap", loc);
          if (native.dark.observer.timeout.g) window.clearTimeout(native.dark.observer.timeout.g);
          native.dark.observer.timeout.g = window.setTimeout(function () {
            if (config.native.mapcssvariables) {
              try {
                if (document.documentElement.computedStyleMap) {
                  let stylemap = document.documentElement.computedStyleMap();
                  if (stylemap) {
                    for (const item of stylemap) {
                      if (item) {
                        if (item[0]) {
                          if (item[1]) {
                            if (item[1][0]) {
                              if (item[1][0][0]) {
                                if (item[0].indexOf(native.dark.theme.css.variable.prefix) === -1) {
                                  native.dark.engine.map.css.object["var(" + item[0] + ")"] = item[1][0][0];
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
                if (config.log) {
                  console.error(e);
                }
              }
            }
          }, native.dark.observer.delay);
        },
        "attributes": function (loc) {
          if (config.log) console.error("attributes", loc);
          if (native.dark.observer.timeout.a) window.clearTimeout(native.dark.observer.timeout.a);
          native.dark.observer.timeout.a = window.setTimeout(function () {
            const list = {};
            try {
              list.attribute = [];
              list.properties = [];
              list.id = document.documentElement.id ? ["#" + document.documentElement.id] : [];
              list.class = document.documentElement.classList.length ? [...document.documentElement.classList].map(e => '.' + e) : [];
              //
              try {
                const attributes = document.documentElement.attributes;
                //
                if (attributes) {
                  if (attributes.length) {
                    for (let i = 0; i < attributes.length; i++) {
                      const item = attributes.item(i);
                      //
                      if (item) {
                        if (item.name) {
                          const cond_1 = item.name !== "id";
                          const cond_2 = item.name !== "class";
                          const cond_3 = item.name !== "style";
                          const cond_4 = item.name !== native.dark.attribute.theme;
                          const cond_5 = item.name !== config.temporarily.id.start;
                          const cond_6 = item.name !== config.temporarily.id.display;
                          const cond_7 = item.name !== config.temporarily.id.brightness;
                          const cond_8 = item.name !== config.temporarily.id.simpledark;
                          //
                          if (cond_1 && cond_2 && cond_3 && cond_4 && cond_5 && cond_6 && cond_7 && cond_8) {
                            if (item.value) {
                              list.attribute.push('[' + item.name + ']');
                              list.attribute.push('[' + item.name + '="' + item.value + '"]');
                            } else {
                              list.attribute.push('[' + item.name + ']');
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
              //
              list.properties = [...list.id, ...list.class, ...list.attribute];
              native.dark.engine.html.attributes.list = list;
            } catch (e) {
              if (config.log) {
                console.error(e);
              }
            }
          }, native.dark.observer.delay);
        }
      },
      "style": {
        "mutation": null,
        "options": {
          "subtree": true,
          "attributes" : true,
          "attributeFilter": ["style"]
        },
        "action": function (node) {
          if (node) {
            try {
              if (node.style) {
                if (node.style.length) {
                  const csstext = node.style.cssText;
                  //
                  if (csstext) {
                    const stylekeys = ["--", "color:", "border-color:", "background:", "background-color:", "background-image:"];
                    //
                    for (let i = 0; i < stylekeys.length; i++) {
                      if (csstext.indexOf(stylekeys[i]) !== -1) {
                        if (native.dark.observer.timeout.d) window.clearTimeout(native.dark.observer.timeout.d);
                        native.dark.observer.timeout.d = window.setTimeout(function () {
                          native.dark.engine.analyze.document.inline.styles();
                        }, native.dark.observer.delay);
                        //
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
          //
          return false;
        },
        "callback": function (mutations) {
          if (mutations) {
            try {
              for (let mutation of mutations) {
                if (mutation.attributeName) {
                  if (mutation.attributeName === "style") {
                    const node = mutation.target;
                    //
                    if (node) {
                      if (node.nodeType === Node.ELEMENT_NODE) {
                        const success = native.dark.observer.style.action(node);
                        if (success) return;
                        //
                        if (config.native.continue === false) {
                          if (document.readyState === "complete") {
                            const nodes = [...node.querySelectorAll("[style]")];
                            //
                            if (nodes) {
                              for (let i = 0; i < nodes.length; i++) {
                                const node = nodes[i];
                                if (node) {
                                  if ([...node.classList].filter(e => e.indexOf("ndcis-") !== -1).length === 0) {
                                    const success = native.dark.observer.style.action(node);
                                    if (success) return;
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
              if (config.log) {
                console.error(e);
              }
            }
          }
        }
      },
      "element": {
        "count": 0,
        "mutation": null,
        "options": {
          "subtree": true,
          "childList": true
        },
        "callback": function (mutations) {
          try {
            for (const mutation of mutations) {
              const nodes = mutation.addedNodes;
              const length = nodes.length;
              //
              native.dark.observer.element.count += length;
              //
              for (let i = 0; i < length; i++) {
                const node = nodes[i];
                const nodetype = node.nodeType;
                //
                if (nodetype === Node.ELEMENT_NODE) {
                  const tagname = node.tagName ? node.tagName.toLowerCase() : '';
                  const nodename = node.nodeName ? node.nodeName.toLowerCase() : '';
                  //
                  const htmlname = tagname || nodename;
                  const cond_1 = htmlname === "link" || htmlname === "style";
                  const cond_2 = htmlname === "iframe" || htmlname === "script";
                  //
                  if (cond_1) {
                    const cloned = native.dark.engine.is.node.cloned(node);
                    if (!cloned) {
                      if (config.log) console.error("process", htmlname);
                      native.dark.engine.analyze.document.node(node, node.sheet, "process", 0);
                    }
                  }
                  //
                  if (config.native.best.performance) {
                    if (cond_1) {
                      if (native.dark.observer.timeout.b) window.clearTimeout(native.dark.observer.timeout.b);
                      native.dark.observer.timeout.b = window.setTimeout(function () {
                        if (config.log) console.error("process", htmlname);
                        //
                        native.dark.observer.root.stylemap(3);
                        native.dark.observer.root.attributes(3);
                      }, native.dark.observer.delay);
                    }
                    //
                    if (cond_2) {
                      if (native.dark.observer.timeout.j) window.clearTimeout(native.dark.observer.timeout.j);
                      native.dark.observer.timeout.j = window.setTimeout(function () {
                        if (config.log) console.error("process", htmlname);
                        native.dark.engine.analyze.document.sheets("process", 1);
                      }, native.dark.observer.delay);
                    }
                  }
                  //
                  if (config.native.continue) {
                    try {
                      const cond_3 = !cond_1 && !cond_2;
                      const cond_4 = document.readyState === "complete";
                      //
                      if (cond_3 && cond_4) {
                        const id = node.id;
                        const name = node.className;
                        //
                        if (id || name) {
                          const cond_6 = id ? native.dark.observer.map[id] === undefined : true;
                          const cond_7 = name ? native.dark.observer.map[name] === undefined : true;
                          //
                          if (cond_6 && cond_7) {
                            if (id) native.dark.observer.map[id] = true;
                            if (name) native.dark.observer.map[name] = true;
                            //
                            if (native.dark.observer.timeout.c) window.clearTimeout(native.dark.observer.timeout.c);
                            native.dark.observer.timeout.c = window.setTimeout(function () {
                              if (config.log) console.error("process", htmlname);
                              native.dark.engine.analyze.document.sheets("process", 2);
                            }, native.dark.observer.delay);
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
          } catch (e) {
            if (config.log) {
              console.error(e);
            }
          }
        }
      }
    },
    "engine": {
      "html": {
        "attributes": {
          "list": {}
        }
      },
      "map": {
        "css": {
          "rules": {},
          "object": {},
          "sheets": {},
          "timeout": null,
          "classnames": {},
          "stylesheets": {},
          "inlinestyles": {},
          "variables": async function (style) {
            try {
              for (let i = 0; i < style.length; i++) {
                const name = style[i].trim();
                const value = (style[name] || style.getPropertyValue(name)).trim();
                //
                if (name && value) {
                  if (name.startsWith("--")) {
                    if (name.indexOf(native.dark.theme.css.variable.prefix) === -1) {
                      native.dark.engine.map.css.object["var(" + name + ")"] = value;
                      //
                      if (config.native.darken.variable.gradient) {
                        if (value.indexOf("-gradient(") !== -1) {
                          if (value.indexOf(config.native.darken.background.shade) === -1) {
                            const property = config.native.darken.background.shade + ", " + value;
                            config.native.stylesheet.insertRule(":root[" + native.dark.attribute.theme + "] {" + name + ':' + property + " !important}", 0);
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
      },
      "add": {
        "class": {
          "modified": function (node, sheet) {
            const local = native.dark.engine.is.node.local(node);
            if (!local) {
              const cloned = native.dark.engine.is.node.cloned(node);
              if (!cloned) {
                const original = native.dark.engine.is.node.original(node);
                if (!original) {
                  const modified = native.dark.engine.is.node.modified(node);
                  if (!modified) {
                    const tagname = node.tagName ? node.tagName.toLowerCase() : '';
                    const nodename = node.nodeName ? node.nodeName.toLowerCase() : '';
                    const htmlname = tagname || nodename;
                    /*  */
                    if (htmlname === "style") {
                      node.classList.add(native.dark.class.modified);
                      native.dark.engine.process.stylesheet(sheet, 3);
                    }
                  }
                }
              }
            }
          }
        }
      },
      "fetch": {
        "stack": {},
        "remote": {
          "css": async function (href, node, index) {
            if (href) {
              try {
                try {
                  if (href.startsWith("http") === false) {
                    href = (new URL(href, document.location.href)).href;
                  }
                } catch (e) {
                  if (config.log) {
                    console.error(e);
                  }
                }
                //
                const cond_0 = href.endsWith(".css");
                const cond_1 = href.startsWith("http");
                const relative = href.replace(/^.*\:\/\//i, '');
                const cond_2 = href.indexOf("font.") === -1 && href.indexOf("font-") === -1 && relative.indexOf("/font") === -1;
                const cond_3 = href.indexOf("fonts.") === -1 && href.indexOf("fonts-") === -1 && relative.indexOf("/fonts") === -1;
                //
                if ((cond_0 && cond_1) || (cond_1 && cond_2 && cond_3)) {
                  if (node) {
                    let original = native.dark.engine.is.node.original(node);
                    if (!original) {
                      node.classList.add(native.dark.class.original);
                    }
                  }
                  //
                  const origin_1 = (new URL(href)).origin;
                  const origin_2 = document.location.origin;
                  native.dark.engine.fetch.stack[href] = node;
                  //
                  if (origin_1 === origin_2) {
                    try {
                      let response = await fetch(href, {"cache": "default"});
                      if (response) {
                        if (response.ok) {
                          let cloned = response.clone();
                          //
                          let content = await response.text();
                          if (content) {
                            if (content.includes("\x00")) {
                              let decoder = new TextDecoder("utf-16");
                              let buffer = await cloned.arrayBuffer();
                              content = buffer ? decoder.decode(buffer) : content;
                            }
                            //
                            native.dark.engine.insert.remote.style(href, content, index);
                          }
                        }
                      }
                    } catch (e) {
                      background.send("fetch", {"href": href, "index": index});
                    }
                  } else {
                    background.send("fetch", {"href": href, "index": index});
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
      },
      "process": {
        "cssstylesheet": async function (src) { // Constructable Stylesheets
          if (src) {
            let script = document.createElement("script");
            script.type = "text/javascript";
            script.onload = function () {script.remove()};
            script.dataset.state = native.dark.engine.is.active ? "active" : "inactive";
            script.src = src;
            /*  */
            document.documentElement.appendChild(script);
          }
        },
        "remote": {
          "style": function (e) {
            if (e) {
              if (e.href) {
                if (e.content) {
                  native.dark.engine.insert.remote.style(e.href, e.content, e.index);
                }
              }
            }
          }
        },
        "stylesheet": async function (sheet, loc) { // Internal & External Stylesheets
          try {
            if (config.addon.state === "dark") {
              if (sheet) {
                if (sheet.cssRules) {
                  const length = sheet.cssRules.length;
                  //
                  for (let index = 0; index < length; index++) {
                    const rule = sheet.cssRules[index];
                    //
                    if (rule) {
                      if (rule.href) {
                        native.dark.engine.fetch.remote.css(rule.href, sheet.ownerNode, index);
                      } else if (rule.style) {
                        native.dark.engine.process.action.normal(rule, sheet);
                      } else {
                        const type = rule.type;
                        const cond_1 = type === window.CSSRule.MEDIA_RULE;
                        const cond_2 = type === window.CSSRule.SUPPORTS_RULE;
                        const cond_3 = type === window.CSSRule.KEYFRAMES_RULE;
                        /*  */
                        if (cond_1 || cond_2 || cond_3) { // i.e. @
                          const cond_4 = cond_2 && config.native.supports;
                          const cond_5 = cond_3 && config.native.keyframes;
                          const cond_6 = cond_1 && config.native.mediaquery;
                          /*  */
                          if (cond_4 || cond_5 || cond_6) {
                            native.dark.engine.process.action.other(rule, sheet, false);
                          }
                        } else {
                          native.dark.engine.process.action.other(rule, sheet, config.native.deeprules);
                        }
                      }
                    }
                  }
                } else {
                  if (config.log) {
                    console.error(rule);
                  }
                }
              } else {
                if (config.log) {
                  console.error(sheet);
                }
              }
            }
          } catch (e) {
            if (config.log) {
              console.error(e);
            }
          }
        },
        "action": {
          "other": async function (rule, sheet, deeper) {
            if (rule) {
              if (rule.cssRules) {
                for (let key of rule.cssRules) {
                  if (key.style) {
                    native.dark.engine.process.action.normal(key, sheet);
                  } else { // i.e. @
                    if (deeper) {
                      const type = key.type;
                      const cond_1 = type === window.CSSRule.MEDIA_RULE;
                      const cond_2 = type === window.CSSRule.SUPPORTS_RULE;
                      const cond_3 = type === window.CSSRule.KEYFRAMES_RULE;
                      /*  */
                      if (cond_1 || cond_2 || cond_3) { // i.e. @
                        const cond_4 = cond_2 && config.native.supports;
                        const cond_5 = cond_3 && config.native.keyframes;
                        const cond_6 = cond_1 && config.native.mediaquery;
                        /*  */
                        if (cond_4 || cond_5 || cond_6) {
                          native.dark.engine.process.action.other(key, sheet, false);
                        }
                      } else {
                        native.dark.engine.process.action.other(key, sheet, config.native.deeprules);
                      }
                    }
                  }
                }
              } else if (rule.styleSheet) {
                native.dark.engine.process.stylesheet(rule.styleSheet, 1);
              } else {
                /* ignore */
              }
            }
          },
          "normal": async function (rule, sheet) {
            if (rule) {
              if (rule.style) {
                const current = rule.style.length;
                const processed = rule[native.dark.class.processed] === current;
                //
                if (!processed) {
                  if (sheet) {
                    let property = {};
                    let base = sheet[native.dark.theme.css.base.url];
                    let shadowroot = sheet[native.dark.attribute.shadowroot];
                    //
                    rule[native.dark.class.processed] = current;
                    if (base) rule[native.dark.theme.css.base.url] = base;
                    sheet[native.dark.class.processed] = sheet.cssRules.length;
                    if (shadowroot) rule[native.dark.attribute.shadowroot] = true;
                    //
                    property.color = rule.style.color || rule.style.getPropertyValue("color");
                    //
                    property.backgroundonly = rule.style.background || rule.style.getPropertyValue("background");
                    //
                    property.svg = (rule.style.fill || rule.style.getPropertyValue("fill")) || 
                                    (rule.style.stroke || rule.style.getPropertyValue("stroke"));
                    //
                    property.image = rule.style.backgroundImage || rule.style.getPropertyValue("background-image");
                    //
                    property.backgroundcolor = rule.style.backgroundColor || rule.style.getPropertyValue("background-color");
                    //
                    property.shadow = (rule.style.boxShadow || rule.style.getPropertyValue("box-shadow")) || 
                                      (rule.style.textShadow || rule.style.getPropertyValue("text-shadow"));
                    //
                    property.border = (rule.style.border || rule.style.getPropertyValue("border")) || 
                                      (rule.style.borderTop || rule.style.getPropertyValue("border-top")) || 
                                      (rule.style.borderLeft || rule.style.getPropertyValue("border-left")) || 
                                      (rule.style.borderColor || rule.style.getPropertyValue("border-color")) || 
                                      (rule.style.borderRight || rule.style.getPropertyValue("border-right")) || 
                                      (rule.style.borderBottom || rule.style.getPropertyValue("border-bottom")) || 
                                      (rule.style.borderTopColor || rule.style.getPropertyValue("border-top-color")) || 
                                      (rule.style.borderLeftColor || rule.style.getPropertyValue("border-left-color")) || 
                                      (rule.style.borderRightColor || rule.style.getPropertyValue("border-right-color")) || 
                                      (rule.style.borderBottomColor || rule.style.getPropertyValue("border-bottom-color")) || 
                                      (rule.style.outline || rule.style.getPropertyValue("outline")) || 
                                      (rule.style.outlineColor || rule.style.getPropertyValue("outline-color"));
                    //
                    if (property.svg) native.dark.engine.apply.style.for["svg"](rule);
                    if (property.color) native.dark.engine.apply.style.for["color"](rule);
                    if (property.shadow) native.dark.engine.apply.style.for["shadow"](rule);
                    if (property.border) native.dark.engine.apply.style.for["border"](rule);
                    if (property.image) native.dark.engine.apply.style.for["background-image"](rule);
                    if (property.backgroundonly) native.dark.engine.apply.style.for["background-only"](rule);
                    if (property.backgroundcolor) native.dark.engine.apply.style.for["background-color"](rule);
                    //
                    if (config.native.mapcssvariables) {
                      native.dark.engine.map.css.variables(rule.style);
                    }
                  }
                }
              }
            }
          }
        },
        "color": function (code, rule, type, method, fallback) {
          if (code === fallback) return code;
          /*  */
          if (config.native.colorful) {
            if (config.native.colorfulmap[type] === true) {
              try {
                if (tinycolor) {
                  let color = code;
                  //
                  if (config.native.mapcssvariables) {
                    if (color.indexOf("--") !== -1) {
                      try {
                        color = color.replace(/(var\(--[a-zA-Z0-9-_]+\))/g, function (match) {
                          const result = native.dark.engine.map.css.object[match];
                          return result !== undefined ? result : match;
                        });
                      } catch (e) {
                        if (config.log) {
                          console.error(e);
                        }
                      }
                      //
                      if (color.indexOf("--") !== -1) {
                        if (color.indexOf("-gradient(") === -1) {
                          if (color.indexOf(',') === -1) {
                            color = native.dark.engine.map.css.object[color];
                            //
                            for (let i = 0; i < 5; i++) {
                              if (color) {
                                if (color.indexOf("--") !== -1) {
                                  color = native.dark.engine.map.css.object[color];
                                } else break;
                              } else break;
                            }
                          } else {
                            try {
                              const colorstring = color.replace("var(", '').replace(')', '').trim();
                              //
                              const colorarray = colorstring.split(/,(.*)/s);
                              const colorkey_1 = colorarray[0].indexOf("--") !== -1 && colorarray[0].indexOf("var(") === -1 ? "var(" + colorarray[0] + ')' : colorarray[0];
                              const colorkey_2 = colorarray[1].indexOf("--") !== -1 && colorarray[1].indexOf("var(") === -1 ? "var(" + colorarray[1] + ')' : colorarray[1];
                              const colorcode_1 = colorkey_1.indexOf("--") !== -1 ? native.dark.engine.map.css.object[colorkey_1] : colorkey_1;
                              const colorcode_2 = colorkey_2.indexOf("--") !== -1 ? native.dark.engine.map.css.object[colorkey_2] : colorkey_2;
                              //
                              color = colorcode_1 ? colorcode_1 : colorcode_2;
                            } catch (e) {
                              if (config.log) {
                                console.error(e);
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                  //
                  if (color) {
                    let isvalid = false;
                    if (color.indexOf("--") === -1) {
                      if (color === "transparent") {
                        return "var(--native-dark-transparent-color)";
                      }
                      /*  */
                      const specs = tinycolor(color);
                      if (specs) {
                        isvalid = specs.isValid();
                        if (isvalid) {
                          const limit = {};
                          const threshold = {};
                          const hsl = specs.toHsl();
                          const text = rule ? rule.selectorText : '';
                          /*  */
                          limit.min = config.native.range.limit.min / 100;
                          limit.max = config.native.range.limit.max / 100;
                          threshold.min = config.native.range.threshold.min / 100;
                          threshold.max = config.native.range.threshold.max / 100;
                          /*  */
                          const hue = hsl.h;
                          const lightness = hsl.l;
                          const saturation = hsl.s;
                          const luminance = specs.getLuminance();
                          const alpha = hsl.a !== undefined ? hsl.a : specs.getAlpha();
                          /*  */
                          const cond_1 = lightness > threshold.max;
                          const cond_2 = ((saturation + lightness) / 2) > threshold.max;
                          const cond_3 = isNaN(saturation) === false && isNaN(lightness) === false && isNaN(alpha) === false;
                          const cond_4 = alpha !== undefined ? (alpha > threshold.max) || (saturation < limit.min && lightness > limit.max) : true;
                          const cond_5 = text ? text.indexOf('.') === -1 && text.split(',').map(e => e.trim()).filter(e => (e === "html" || e === "body")).length > 0 : false;
                          const isbright = (cond_3 && cond_4 && (cond_1 || cond_2));
                          /*  */
                          if (alpha < limit.min) {
                            return color;
                          } else {
                            if (luminance > threshold.max || (cond_3 && cond_4 && cond_5)) {
                              if (config.native.force.color.transparency) {
                                if (alpha < 1) {
                                  return "color-mix(in srgb, " + fallback + ", transparent " + Math.floor((1 - alpha) * 100) +"%)";
                                } else {
                                  if (config.native.force.color.closetowhite) {
                                    const brighter = {};
                                    brighter.strength = 105; // strength multiplier
                                    brighter.exponent = 1.10; // how quickly the percentage rises
                                    brighter.min = Number(config.native.force.color.closetowhitemin);
                                    brighter.max = Number(config.native.force.color.closetowhitemax);
                                    brighter.percent = Math.floor(isbright ? Math.min(100, Math.pow(Math.max(0, Math.min(1, (lightness - threshold.max) / (1 - threshold.max))), brighter.exponent) * brighter.strength) : 0);
                                    /*  */
                                    if (brighter.percent >= brighter.min && brighter.percent <= brighter.max) {
                                      const hex = config.native.css.variables[fallback.slice(4, -1).trim()];
                                      /*  */
                                      if (hex && /^#[0-9a-f]{6}$/i.test(hex)) {
                                        const darker = {};
                                        darker.percent = Number(config.native.force.color.closetowhitepercent);
                                        darker.percent = Math.floor(darker.percent * (brighter.percent / 100));
                                        darker.r = Math.max(0, parseInt(hex.slice(1, 3), 16) - darker.percent);
                                        darker.g = Math.max(0, parseInt(hex.slice(3, 5), 16) - darker.percent);
                                        darker.b = Math.max(0, parseInt(hex.slice(5, 7), 16) - darker.percent);
                                        darker.fallback = "#" + darker.r.toString(16).padStart(2, '0') + darker.g.toString(16).padStart(2, '0') + darker.b.toString(16).padStart(2, '0');
                                        /*  */
                                        return "color-mix(in srgb, " + fallback + " " + (100 - brighter.percent) + "%, " + darker.fallback + " " + brighter.percent + "%)";
                                      } else {
                                        return fallback;
                                      }
                                    } else {
                                      return fallback;
                                    }
                                  } else {
                                    return fallback;
                                  }
                                }
                              } else {
                                return fallback;
                              }
                            } else if (luminance > threshold.min) {
                              let percent = 10;
                              if (isbright && method === "darken") percent = 50;
                              const tmp = method === "lighten" ? specs.lighten(percent) : specs.darken(percent);
                              return tmp.toHex8String();
                            } else { // luminance <= threshold.min
                              if (luminance === 0) return color;
                              /*  */
                              if (isbright) { // very bright
                                if (config.native.force.color.transparency) {
                                  return alpha < 1 ? "color-mix(in srgb, " + fallback + ", transparent " + Math.floor((1 - alpha) * 100) +"%)" : fallback;
                                } else {
                                  return fallback;
                                }
                              }
                              /*  */
                              if (config.native.force.color.background) {
                                return color;
                              }
                            }
                          }
                        } else {
                          //
                        }
                      }
                    }
                    //
                    if (color.indexOf("-gradient(") !== -1) {
                      if (config.native.remove.background.color) {
                        return fallback;
                      }
                      //
                      if (config.native.darken.background.gradient) {
                        return config.native.darken.background.shade + ", " + color;
                      }
                    }
                    //
                    if (isvalid === false) {
                      if (config.native.backgroundfallback) {
                        const transparency = config.native.backgroundtransparency !== undefined ? Number(config.native.backgroundtransparency) : 10;
                        return "color-mix(in srgb, " + fallback + ' ' + (100 - transparency) + "%, transparent)";
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
          /*  */
          return fallback;
        }
      },
      "analyze": {
        "document": {
          "inline": {
            "styles": function () {
              const nodes = [...document.querySelectorAll("[style]")];
              if (nodes) {
                for (let i = 0; i < nodes.length; i++) {
                  const node = nodes[i];
                  const tagname = node.tagName ? node.tagName.toLowerCase() : '';
                  const nodename = node.nodeName ? node.nodeName.toLowerCase() : '';
                  const htmlname = tagname || nodename;
                  //
                  native.dark.engine.insert.rule.inline(node, htmlname);
                }
              }
            }
          },
          "sheets": async function (key, loc) {
            if (key) {
              if (config.native.checkstylesheet) {
                config.check.darkmode.native.styles(loc);
              }
              //
              const sheets = document.styleSheets;
              if (sheets) { // #1
                for (const sheet of sheets) {
                  const node = sheet.ownerNode;
                  native.dark.engine.analyze.document.node(node, sheet, key, loc);
                }
              }
              //
              if (key === "process") {
                if (config.native.selected) {
                  if (config.native.inline) { // #2
                    native.dark.engine.analyze.document.inline.styles();
                  }
                  /*  */
                  if (config.native.cssstylesheet) { // #3
                    if (config.native.shadow.sheets) {
                      if (config.native.shadow.sheets.length) {
                        for (let i = 0; i < config.native.shadow.sheets.length; i++) {
                          const sheet = config.native.shadow.sheets[i];
                          if (sheet) {
                            if (sheet[native.dark.class.processed] === undefined) {
                              native.dark.engine.process.stylesheet(sheet, 5);
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
          "node": function (node, sheet, key, loc) {
            if (node) {
              const local = native.dark.engine.is.node.local(node);
              if (!local) {
                const original = native.dark.engine.is.node.original(node);
                if (!original) {
                  const tagname = node.tagName.toLowerCase();
                  const nodename = node.nodeName.toLowerCase();
                  const cond_1 = tagname === "link" || nodename === "link";
                  const cond_2 = tagname === "style" || nodename === "style";
                  /*  */
                  if (cond_1 || cond_2) {
                    const cloned = native.dark.engine.is.node.cloned(node);
                    const modified = native.dark.engine.is.node.modified(node);
                    const processed = native.dark.engine.is.sheet.processed(sheet);
                    /*  */
                    if (key === "clean") {
                      if (cloned) {
                        if (sheet) sheet.disabled = true;
                        node.setAttribute("disabled", '');
                      }
                    }
                    /*  */
                    if (key === "process") {
                      if (cloned) {
                        if (sheet) sheet.disabled = false;
                        node.removeAttribute("disabled");
                      }
                      /*  */
                      if (!processed) {
                        if (cond_1) {
                          const href = {};
                          href.a = sheet && sheet.href ? sheet.href : '';
                          href.b = node.type === "text/css" || node.rel === "stylesheet" ? node.href : '';
                          href.c = href.a || href.b;
                          //
                          native.dark.engine.fetch.remote.css(href.c, node, 0);
                        }
                        /*  */
                        if (cond_2) {
                          if (cloned || modified) {
                            native.dark.engine.process.stylesheet(sheet, 2);
                          } else {
                            native.dark.engine.add.class.modified(node, sheet);
                          }
                        }
                      }
                    }
                  } else {
                    if (config.log) {
                      console.error(sheet);
                    }
                  }
                }
              }
            } else {
              if (config.log) {
                console.error(sheet);
              }
            }
          }
        }
      },
      "is": {
        "active": false,
        "sheet": {
          "processed": function (sheet) {
            try {
              return sheet && sheet.cssRules ? sheet[native.dark.class.processed] === sheet.cssRules.length : false;
            } catch (e) {
              if (config.log) {
                console.error(e);
              }
            }
            //
            return false;
          }
        },
        "node": {
          "cloned": function (node) {
            return node && node.classList.contains(native.dark.class.cloned);
          },          
          "modified": function (node) {
            return node && node.classList.contains(native.dark.class.modified);
          },
          "original": function (node) {
            return node && node.classList.contains(native.dark.class.original);
          },
          "local": function (node) {
            const cond_a = node && node.id && node.id === "dark-mode-custom-link";
            const cond_b = node && node.id && node.id === "dark-mode-general-link";
            const cond_c = node && node.id && node.id === "dark-mode-custom-style";
            const cond_d = node && node.id && node.id === "dark-mode-native-style";
            const cond_e = node && node.id && node.id === "dark-mode-native-sheet";
            /*  */
            return cond_a || cond_b || cond_c || cond_d || cond_e;
          }
        },
        "color": {
          "valid": {
            "for": {
              "font": {
                "color": function (e) {
                  if (e) {
                    try {
                      e = e.toLowerCase();
                      /*  */
                      if (e.indexOf("--") !== -1) return true;
                      //
                      if (e.indexOf("inherit") === -1) {
                        if (e.indexOf("window") === -1) {
                          if (e.indexOf("windowtext") === -1) {
                            if (e.indexOf("currentcolor") === -1) {
                              return true;
                            }
                          }
                        }
                      }
                    } catch (e) {
                      return false;
                    }
                  }
                  /*  */
                  return false;
                }
              },
              "svg": {
                "color": function (e) {
                  if (e) {
                    try {
                      e = e.toLowerCase();
                      /*  */
                      if (e.indexOf("--") !== -1) return true;
                      //
                      if (e.indexOf("none") === -1) {
                        if (e.indexOf("unset") === -1) {
                          if (e.indexOf("inherit") === -1) {
                            if (e.indexOf("window") === -1) {
                              if (e.indexOf("windowtext") === -1) {
                                if (e.indexOf("transparent") === -1) {
                                  if (e.indexOf("currentcolor") === -1) {
                                    return true;
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
                  /*  */
                  return false;
                }
              },
              "border": function (e) {
                if (e) {
                  try {
                    e = e.toLowerCase();
                    /*  */
                    if (e.indexOf("--") !== -1) return true;
                    //
                    if (e.indexOf("none") === -1) {
                      if (e.indexOf("unset") === -1) {
                        if (e.indexOf("inherit") === -1) {
                          if (e.indexOf("initial") === -1) {
                            if (e.indexOf("window") === -1) {
                              if (e.indexOf("windowtext") === -1) {
                                if (e.indexOf("transparent") === -1) {
                                  if (e.indexOf("currentcolor") === -1) {
                                    return true;
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
                /*  */
                return false;
              },
              "background": {
                "url": function (e) {
                  if (e) {
                    try {
                      e = e.toLowerCase();
                      /*  */
                      if (e.indexOf("url(") !== -1) {
                        return true;
                      }
                    } catch (e) {
                      return false;
                    }
                  }
                  /*  */
                  return false;
                },
                "color": function (e) {
                  if (e) {
                    try {
                      e = e.toLowerCase();
                      /*  */
                      if (e.indexOf("-gradient(") !== -1) return (config.native.remove.background.color || config.native.darken.background.gradient);
                      if (e.indexOf("--") !== -1) return true;
                      //
                      if (e.indexOf("none") === -1) {
                        if (e.indexOf("unset") === -1) {
                          if (e.indexOf("black") === -1) {
                            if (e.indexOf("url(") === -1) {
                              if (e.indexOf("inherit") === -1) {
                                if (e.indexOf("initial") === -1) {
                                  if (e.indexOf("window") === -1) {
                                    if (e.indexOf("windowtext") === -1) {
                                      if (e.indexOf("currentcolor") === -1) {
                                        if (e.indexOf("-gradient(") === -1) {
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
                    } catch (e) {
                      return false;
                    }
                  }
                  /*  */
                  return false;
                }
              }
            }
          }
        }
      },
      "apply": {
        "style": {
          "for": {
            "shadow": function (rule) {
              if (rule.style) {
                if (config.native.force.color.textshadow) {
                  var tmp = rule.style.textShadow || rule.style.getPropertyValue("text-shadow");
                  if (tmp && tmp !== "var(--native-dark-text-shadow)") {
                    native.dark.engine.insert.rule.custom(rule, "text-shadow", "var(--native-dark-text-shadow)", '');
                  }
                }
                //
                if (config.native.force.color.boxshadow) {
                  var tmp = rule.style.boxShadow || rule.style.getPropertyValue("box-shadow");
                  if (tmp && tmp !== "none" && tmp.indexOf("transparent") === -1 && tmp !== "var(--native-dark-box-shadow)") {
                    native.dark.engine.insert.rule.custom(rule, "box-shadow", "var(--native-dark-box-shadow)", '');
                  }
                }
              }
            },
            "color": function (rule) {
              if (rule.style) {
                if (config.native.force.color.font) {
                  var tmp = rule.style.color || rule.style.getPropertyValue("color");
                  if (native.dark.engine.is.color.valid.for.font.color(tmp)) {
                    if (tmp && tmp !== "var(--native-dark-font-color)") {
                      if (tmp.indexOf("transparent") === -1) {
                        const value = native.dark.engine.process.color(tmp, rule, "font", "lighten", "var(--native-dark-font-color)");
                        native.dark.engine.insert.rule.custom(rule, "color", value, '');
                      } else {
                        native.dark.engine.insert.rule.custom(rule, "font-size", "0", '');
                      }
                    }
                  }
                }
              }
            },
            "svg": function (rule) {
              if (rule.style) {
                if (config.native.force.color.svgfill) {
                  var tmp = rule.style.fill || rule.style.getPropertyValue("fill");
                  if (tmp && tmp !== "var(--native-dark-fill-color)") {
                    if (native.dark.engine.is.color.valid.for.svg.color(tmp)) {
                      const value = native.dark.engine.process.color(tmp, rule, "svg", "lighten", "var(--native-dark-fill-color)");
                      native.dark.engine.insert.rule.custom(rule, "fill", value, '');
                    }
                  }
                }
                //
                if (config.native.force.color.svgstroke) {
                  var tmp = rule.style.stroke || rule.style.getPropertyValue("stroke");
                  if (tmp && tmp !== "var(--native-dark-fill-color)") {
                    if (native.dark.engine.is.color.valid.for.svg.color(tmp)) {
                      const value = native.dark.engine.process.color(tmp, rule, "svg", "lighten", "var(--native-dark-fill-color)");
                      native.dark.engine.insert.rule.custom(rule, "stroke", value, '');
                    }
                  }
                }
              }
            },
            "background-color": function (rule) {
              if (rule.style) {
                if (config.native.force.color.backgroundcolor) {
                  var tmp = rule.style.backgroundColor || rule.style.getPropertyValue("background-color");
                  if (tmp) {
                    if (native.dark.engine.is.color.valid.for.background.color(tmp)) {
                      const value = native.dark.engine.process.color(tmp, rule, "background", "darken", "var(--native-dark-bg-color)");
                      if (tmp !== value || tmp === "transparent") {
                        native.dark.engine.insert.rule.custom(rule, "background-color", value, '');
                        //
                        if (config.native.backgroundblend) {
                          native.dark.engine.insert.rule.custom(rule, "background-blend-mode", "var(--native-dark-bg-blend-mode)", '');
                        }
                      } else {

                      }
                    }
                  }
                }
              }
            },
            "background-only": function (rule) {
              if (rule.style) {
                var tmp = rule.style.background || rule.style.getPropertyValue("background");
                if (tmp) {
                  if (config.native.force.color.backgroundcolor) {
                    if (native.dark.engine.is.color.valid.for.background.color(tmp)) {
                      const value = native.dark.engine.process.color(tmp, rule, "background", "darken", "var(--native-dark-bg-color)");
                      if (tmp !== value || tmp === "transparent") {
                        const nobc = rule.style.getPropertyValue("background-color") === '';
                        const key = nobc ? "background" : (tmp.indexOf("-gradient(") !== -1 ? "background" : "background-color");
                        native.dark.engine.insert.rule.custom(rule, key, value, '');
                      }
                    }
                  }
                  //
                  if (config.native.darken.background.image) {
                    if (native.dark.engine.is.color.valid.for.background.url(tmp)) {
                      native.dark.engine.insert.rule.for.image(rule, "background", tmp);
                    }
                  }
                }
              }
            },
            "background-image": function (rule) {
              if (rule.style) {
                var tmp = rule.style.backgroundImage || rule.style.getPropertyValue("background-image");
                if (tmp && tmp !== "none") {
                  if (tmp.indexOf("url(") === -1) {
                    if (tmp.indexOf("-gradient(") !== -1) {
                      if (config.native.remove.background.image) {
                        native.dark.engine.insert.rule.custom(rule, "background-image", "none", '');
                      }
                    }
                  } else {
                    if (config.native.darken.background.image) {
                      native.dark.engine.insert.rule.for.image(rule, "background-image", tmp);
                      //
                      if (config.native.backgroundrelated) {
                        const add = {};
                        const repeat = rule.style.backgroundRepeat || rule.style.getPropertyValue("background-repeat");
                        const position = rule.style.backgroundPosition || rule.style.getPropertyValue("background-position");
                        //
                        add.repeat = repeat ? (repeat === "initial" && config.native.backgroundinitial ? false : true) : false;
                        add.position = position ? (position === "initial" && config.native.backgroundinitial ? false : true) : false;
                        //
                        if (add.repeat) native.dark.engine.insert.rule.custom(rule, "background-repeat", repeat, '');
                        if (add.position) native.dark.engine.insert.rule.custom(rule, "background-position", position, '');
                      }
                    }
                  }
                }
              }
            },
            "border": function (rule) {
              if (rule.style) {
                if (config.native.force.color.border) {
                  var a = rule.style.outline || rule.style.getPropertyValue("outline");
                  var c = rule.style.outlineColor || rule.style.getPropertyValue("outline-color");
                  var b = config.native.force.width.border ? (rule.style.outlineWidth || rule.style.getPropertyValue("outline-width")) : true;
                  /*  */
                  if ((a && b) || c) {
                    var tmp = c ? c : a;
                    if (tmp && tmp !== "var(--native-dark-border-color)") {
                      if (native.dark.engine.is.color.valid.for.border(tmp)) {
                        const value = native.dark.engine.process.color(tmp, rule, "border", "darken", "var(--native-dark-border-color)");
                        native.dark.engine.insert.rule.custom(rule, "outline-color", value, '');
                      }
                    }
                  }
                  /*  */
                  var a = rule.style.border || rule.style.getPropertyValue("border");
                  var c = rule.style.borderColor || rule.style.getPropertyValue("border-color");
                  var b = config.native.force.width.border ? (rule.style.borderWidth || rule.style.getPropertyValue("border-width")) : true;
                  /*  */
                  if ((a && b) || c) {
                    var tmp = c ? c : a;
                    if (tmp && tmp !== "var(--native-dark-border-color)") {
                      if (native.dark.engine.is.color.valid.for.border(tmp)) {
                        const value = native.dark.engine.process.color(tmp, rule, "border", "darken", "var(--native-dark-border-color)");
                        native.dark.engine.insert.rule.custom(rule, "border-color", value, '');
                      }
                    }
                  }
                  /*  */
                  var a = rule.style.borderTop || rule.style.getPropertyValue("border-top");
                  var c = rule.style.borderTopColor || rule.style.getPropertyValue("border-top-color");
                  var b = config.native.force.width.border ? (rule.style.borderTopWidth || rule.style.getPropertyValue("border-top-width")) : true;
                  /*  */
                  if ((a && b) || c) {
                    var tmp = c ? c : a;
                    if (tmp && tmp !== "var(--native-dark-border-color)") {
                      if (native.dark.engine.is.color.valid.for.border(tmp)) {
                        const value = native.dark.engine.process.color(tmp, rule, "border", "darken", "var(--native-dark-border-color)");
                        native.dark.engine.insert.rule.custom(rule, "border-top-color", value, '');
                      }
                    }
                  }
                  /*  */
                  var a = rule.style.borderLeft || rule.style.getPropertyValue("border-left");
                  var c = rule.style.borderLeftColor || rule.style.getPropertyValue("border-left-color");
                  var b = config.native.force.width.border ? (rule.style.borderLeftWidth || rule.style.getPropertyValue("border-left-width")) : true;
                  /*  */
                  if ((a && b) || c) {
                    var tmp = c ? c : a;
                    if (tmp && tmp !== "var(--native-dark-border-color)") {
                      if (native.dark.engine.is.color.valid.for.border(tmp)) {
                        const value = native.dark.engine.process.color(tmp, rule, "border", "darken", "var(--native-dark-border-color)");
                        native.dark.engine.insert.rule.custom(rule, "border-left-color", value, '');
                      }
                    }
                  }
                  /*  */
                  var a = rule.style.borderRight || rule.style.getPropertyValue("border-right");
                  var c = rule.style.borderRightColor || rule.style.getPropertyValue("border-right-color");
                  var b = config.native.force.width.border ? (rule.style.borderRightWidth || rule.style.getPropertyValue("border-right-width")) : true;
                  /*  */
                  if ((a && b) || c) {
                    var tmp = c ? c : a;
                    if (tmp && tmp !== "var(--native-dark-border-color)") {
                      if (native.dark.engine.is.color.valid.for.border(tmp)) {
                        const value = native.dark.engine.process.color(tmp, rule, "border", "darken", "var(--native-dark-border-color)");
                        native.dark.engine.insert.rule.custom(rule, "border-right-color", value, '');
                      }
                    }
                  }
                  /*  */
                  var a = rule.style.borderBottom || rule.style.getPropertyValue("border-bottom");
                  var c = rule.style.borderBottomColor || rule.style.getPropertyValue("border-bottom-color");
                  var b = config.native.force.width.border ? (rule.style.borderBottomWidth || rule.style.getPropertyValue("border-bottom-width")) : true;
                  /*  */
                  if ((a && b) || c) {
                    var tmp = c ? c : a;
                    if (tmp && tmp !== "var(--native-dark-border-color)") {
                      if (native.dark.engine.is.color.valid.for.border(tmp)) {
                        const value = native.dark.engine.process.color(tmp, rule, "border", "darken", "var(--native-dark-border-color)");
                        native.dark.engine.insert.rule.custom(rule, "border-bottom-color", value, '');
                      }
                    }
                  }
                }
              }
            }
          }
        }
      },
      "insert": {
        "remote": {
          "style": async function (href, content, index) {
            if (content.indexOf("<!DOCTYPE html>") !== -1) return;
            /*  */
            let style = document.createElement("style");
            let parent = config.native.documentroot ? document.documentElement : document.head;
            /*  */
            try {
              content = content.replace(native.dark.regexp.relative, function (match, paran1, paran2) {
                try {
                  return "url('" + (new URL(paran2, href)).href + "')";
                } catch (e) {
                  if (config.log) {
                    console.error(e);
                  }
                }
                //
                return match;
              });
            } catch (e) {
              if (config.log) {
                console.error(e);
              }
            }
            /*  */
            style.textContent = content;
            style.setAttribute("lang", "en");
            style.setAttribute("type", "text/css");
            style.setAttribute("native-dark-index", index);
            style.classList.add(native.dark.class.cloned);
            /*  */
            let node = native.dark.engine.fetch.stack[href];
            if (node) {
              if (node.media) style.setAttribute("media", node.media);
              node.appendChild(style);
              //node.parentNode.insertBefore(style, node.nextSibling);
            } else {
              parent.appendChild(style);
            }
            /*  */
            const _processstyle = function (style) {
              if (style) {
                if (style.sheet) {
                  style.sheet[native.dark.theme.css.base.url] = href;
                  native.dark.engine.process.stylesheet(style.sheet, 4);
                }
              }
            };
            /*  */
            const _checkstyle = function (style) {
              if (style) {
                if (style.sheet) {
                  _processstyle(style);
                } else {
                  window.requestAnimationFrame(function () {
                    if (style.sheet) {
                      _processstyle(style);
                    }
                  });
                }
              }
            };
            /*  */
            _checkstyle(style);
          }
        },
        "rule": {
          "for": {
            "node": function (node, name, value, classname) {
              try {
                if (classname) {
                  const selector = "html[" + native.dark.attribute.theme + "]" + " ." + classname;
                  const cssrulestring = selector + ' ' + "{" + name + ": " + value + " !important}";
                  //
                  if (native.dark.engine.map.css.rules[cssrulestring] === undefined) {
                    index = config.native.stylesheet.insertRule(cssrulestring, 0);
                    native.dark.engine.map.css.rules[selector] = index;
                    native.dark.engine.map.css.rules[cssrulestring] = index;
                  }
                }
              } catch (e) {
                if (config.log) {
                  console.error(e);
                }
              }
            },
            "image": function (rule, name, value) {
              try {
                let item = '';
                value = decodeURIComponent(value);
                name = value.indexOf("url(") === 0 ? "background-image" : name;
                //
                if (native.dark.regexp.check.test(value) === false) {
                  if (value.indexOf("data:image/svg") !== -1) {
                    item = 'a';
                    //
                    const o_color = native.dark.regexp.color.exec(value)[0].trim();
                    const c_color = tinycolor(config.native.css.variables["--native-dark-fill-color"]).toRgbString();
                    const n_color = native.dark.engine.process.color(o_color, '', "background", "lighten", c_color);
                    value = value.replace(o_color, n_color);
                  } else {
                    item = 'c';
                    value = native.dark.regexp.url.exec(value)[0].trim();
                  }
                  //
                  const option = {
                    'a': [name, value],
                    'b': ["filter", "var(--native-dark-bg-image-filter)"],
                    'c': [name, "linear-gradient(var(--native-dark-bg-image-color), var(--native-dark-bg-image-color)), " + value]
                  };
                  //
                  if (rule) {
                    const text = rule.selectorText;
                    const ishtml = text.startsWith("html");
                    const isbody = text.startsWith("body");
                    const pseudo = text.indexOf("::") !== -1;
                    //
                    if (ishtml && pseudo) {
                      native.dark.engine.insert.rule.custom(rule, option.b[0], option.b[1], "html");
                    } else if (isbody && pseudo) {
                      native.dark.engine.insert.rule.custom(rule, option.b[0], option.b[1], "body");
                    } else {
                      native.dark.engine.insert.rule.custom(rule, option[item][0], option[item][1], '');
                    }
                  } else {
                    return option[item][1];
                  }
                } else {
                  return value;
                }
              } catch (e) {
                return value;
              }
            }
          },
          "inline": async function (node, htmlname) {
            if (node) {
              try {
                if (node.nodeType) {
                  if (node.nodeType === Node.ELEMENT_NODE) {
                    if (node.style) {
                      if (node.style.length) {
                        let classname = [...node.classList].filter(e => e.indexOf("ndcis-") !== -1)[0];
                        if (classname === undefined) {
                          classname = "ndcis-" + Math.floor(Math.random() * 1e7);
                          node.classList.add(classname);
                        }
                        //
                        let current = native.dark.engine.map.css.inlinestyles[classname] || {};
                        //
                        for (let i = 0; i < node.style.length; i++) {
                          try {
                            let value = '';
                            const key = node.style[i];
                            //
                            if (key) {
                              if (current[key] === undefined) {
                                if (config.native.mapcssvariables) {
                                  if (key.startsWith("--")) {
                                    if (key.indexOf(native.dark.theme.css.variable.prefix) === -1) {
                                      value = node.style.getPropertyValue(key);
                                      native.dark.engine.map.css.object["var(" + key + ")"] = value;
                                    }
                                  }
                                }
                                //
                                if (key === "color") {
                                  value = node.style.getPropertyValue(key);
                                  value = native.dark.engine.process.color(value, '', "font", "lighten", "var(--native-dark-font-color)");
                                  native.dark.engine.insert.rule.for.node(node, key, value, classname);
                                }
                                //
                                if (key === "border-color") {
                                  value = node.style.getPropertyValue(key);
                                  value = native.dark.engine.process.color(value, '', "border", "darken", "var(--native-dark-border-color)");
                                  native.dark.engine.insert.rule.for.node(node, key, value, classname);
                                }
                                //
                                if (key === "background" || key === "background-color") {
                                  value = node.style.getPropertyValue(key);
                                  value = native.dark.engine.process.color(value, '', "background", "darken", "var(--native-dark-bg-color)");
                                  native.dark.engine.insert.rule.for.node(node, key, value, classname);
                                }
                                //
                                if (key === "background-image") {
                                  if (config.native.darken.background.image) {
                                    value = node.style.getPropertyValue(key);
                                    value = native.dark.engine.insert.rule.for.image(null, "background-image", value);
                                    native.dark.engine.insert.rule.for.node(node, key, value, classname);
                                  }
                                }
                                //
                                current[key] = value ? value : "N/A";
                                native.dark.engine.map.css.inlinestyles[classname] = current;
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
                }
              } catch (e) {
                if (config.log) {
                  console.error(e);
                }
              }
            }
          },
          "custom": async function (rule, name, value, match) {
            try {
              if (name) {
                if (rule.type === window.CSSRule.KEYFRAME_RULE) {
                  if (config.native.keyframes) {
                    try {
                      const parentrule = rule.parentRule;
                      //
                      if (parentrule) {
                        if (parentrule.name) {
                          const selector = "@keyframes" + ' ' + parentrule.name;
                          let index = native.dark.engine.map.css.rules[selector];
                          //
                          if (index === undefined) {
                            let rulestext = '';
                            const cssrules = parentrule.cssRules;
                            //
                            for (let i = 0; i < cssrules.length; i++) {
                              rulestext += cssrules[i].cssText + '\n';
                            }
                            //
                            const cssrulestring = selector + ' ' + '{' + '\n' + rulestext + '}';
                            index = config.native.stylesheet.insertRule(cssrulestring, 0);
                            native.dark.engine.map.css.rules[selector] = index;
                          }
                          //
                          const current = config.native.stylesheet.rules[index];
                          for (let i = 0; i < current.length; i++) {
                            if (rule.keyText === current[i].keyText) {
                              if (current[i][name] === undefined) {
                                current[i].style.setProperty(name, value);
                                current[i][name] = value;
                                break;
                              }
                            }
                          }
                          //
                          return;
                        }
                      }
                    } catch (e) {
                      if (config.log) {
                        console.error(e);
                      }
                    }
                  }
                } else {
                  const selectortext = rule.selectorText;
                  //
                  if (selectortext) {
                    const chunks = [];
                    const items = selectortext.split(',');
                    const list = native.dark.engine.html.attributes.list;
                    const shadowroot = rule[native.dark.attribute.shadowroot];
                    //
                    for (let i = 0; i < items.length; i++) {
                      const item = items[i];
                      //
                      if (item) {
                        let text = item.trim();
                        if (text) {
                          const firstclass = text.split(' ')[0];
                          //
                          const cond_1 = text.startsWith('*');
                          const cond_7 = text.startsWith('[');
                          const cond_2 = text.startsWith("::");
                          const cond_3 = text.startsWith("html");
                          const cond_9 = text.startsWith(":root");
                          const cond_8 = text.indexOf(">") === -1;
                          const cond_10 = text.startsWith(":host");
                          const cond_4 = text.startsWith(".") && text.endsWith("body");
                          const cond_5 = list.properties && list.properties.length ? list.properties.indexOf(firstclass) !== -1 : false;
                          const cond_6 = text.indexOf("-body") === -1 && text.indexOf("body-") === -1;
                          //
                          const separator = cond_9 ? '' : " ";
                          const keyhtml = "html[" + native.dark.attribute.theme + "]";
                          const keyroot = ":root[" + native.dark.attribute.theme + "]";
                          const keyhost = ":host([" + native.dark.attribute.theme + "])";
                          const keyglobal = shadowroot ? (cond_10 ? keyhost : '') : keyhtml;
                          //
                          if (cond_1) {
                            text = (text === '*' ? keyglobal + ', ' : '') + keyglobal + separator + text;
                          } else if (cond_2) {
                            text = '';
                          } else if (cond_3) {
                            text = text.replace("html", keyhtml);
                          } else if (cond_10) {
                            const simple = text.indexOf(')') === -1;
                            const complement = '[' + native.dark.attribute.theme + "])";
                            text = simple ? text.replace(":host", keyhost) : text.replace(')', complement);
                          } else {
                            if (cond_5) {
                              const querycount = [...document.querySelectorAll(firstclass)].length + 1;
                              //
                              if (querycount === 1) {
                                text = keyglobal + (cond_8 ? '' : " ") + text;
                              } else {
                                if (cond_8) {
                                  text = keyglobal + '' + text + ', ' + keyglobal + " " + text;
                                } else {
                                  text = keyglobal + " " + text;
                                }
                              }
                            } else if (cond_7) {
                              text = keyglobal + (cond_8 ? (cond_5 ? '' : separator) : separator) + text;
                            } else {
                              text = keyglobal + separator + text;
                            }
                          }
                          //
                          if (text) {
                            chunks.push(text);
                          }
                        }
                      }
                    }
                    //
                    const selector = chunks.join(", ");
                    //
                    if (selector) {
                      let hassupports = false;
                      let hasmediaquery = false;
                      //
                      const priority = rule.style.getPropertyPriority(name);
                      const cssrulebody = name + ": " + (value ? value : "var(--native-dark-bg-color)");
                      const postfix = config.native.priority ? " !important" : (priority ? " !" + priority : '');
                      //
                      let cssrulestring = selector + " " + "{" + cssrulebody + postfix + "}";
                      let cssrulechecksum = selector + " " + "{" + cssrulebody + " !important" + "}";
                      //
                      if (config.native.supports || config.native.mediaquery) {
                        try {
                          const parentrule = rule.parentRule;
                          //
                          if (parentrule) {
                            const conditiontext = parentrule.conditionText;
                            //
                            if (conditiontext) {
                              const type = parentrule.type;
                              //
                              if (type === window.CSSRule.SUPPORTS_RULE) {
                                hassupports = true;
                                cssrulestring = "@supports " + conditiontext + " {" + cssrulestring + "}";
                              }
                              //
                              if (type === window.CSSRule.MEDIA_RULE) {
                                hasmediaquery = true;
                                cssrulestring = "@media " + conditiontext + " {" + cssrulestring + "}";
                              }
                            }
                          }
                        } catch (e) {
                          if (config.log) {
                            console.error(e);
                          }
                        }
                      }
                      //
                      if (native.dark.engine.map.css.rules[cssrulestring] === undefined) {
                        const cond_1 = selectortext.indexOf(".") === -1;
                        const cond_2 = selectortext.indexOf(",") === -1;
                        const cond_3 = match ? selectortext.startsWith(match) : false;
                        //
                        if (match === '' || (cond_1 && cond_2 && cond_3)) {
                          try {
                            let index = native.dark.engine.map.css.rules[selector];
                            let sheet = shadowroot ? rule.parentStyleSheet[native.dark.object.cssstylesheet] : config.native.stylesheet;
                            //
                            if (sheet) {
                              if (config.native.temporarily.action) {
                                if (config.temporarily.is.slow === false && config.temporarily.is.removed === false) {
                                  if (sheet.cssRules.length) {
                                    const threshold = config.native.temporarily.threshold !== undefined ? Number(config.native.temporarily.threshold) : 1000;
                                    //
                                    if (native.dark.observer.element.count < threshold) {
                                      const delay = config.native.temporarily.delay !== undefined ? Number(config.native.temporarily.delay) : 200;
                                      //
                                      config.temporarily.is.removed = true;
                                      config.temporarily.remove(delay, 7);
                                    } else {
                                      config.temporarily.is.slow = true;
                                    }
                                  }
                                }
                              }
                              //
                              if (index === undefined || hassupports === true || hasmediaquery === true) {
                                index = sheet.insertRule(cssrulestring, 0);
                                native.dark.engine.map.css.rules[selector] = index;
                                native.dark.engine.map.css.rules[cssrulestring] = index;
                              } else {
                                try {
                                  for (let i = 0; i < sheet.cssRules.length; i++) {
                                    if (sheet.cssRules[i].selectorText === selector) {
                                      const checksum = native.dark.engine.map.css.rules[cssrulechecksum];
                                      //
                                      native.dark.engine.map.css.rules[selector] = i;
                                      native.dark.engine.map.css.rules[cssrulestring] = i;
                                      return checksum === undefined ? sheet.cssRules[i].style.setProperty(name, value, config.native.priority ? "important" : priority) : '';
                                    }
                                  }
                                  //
                                  index = sheet.insertRule(cssrulestring, 0);
                                  native.dark.engine.map.css.rules[selector] = index;
                                  native.dark.engine.map.css.rules[cssrulestring] = index;
                                } catch (e) {
                                  index = sheet.insertRule(cssrulestring, 0);
                                  native.dark.engine.map.css.rules[selector] = index;
                                  native.dark.engine.map.css.rules[cssrulestring] = index;
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
  }
};

native.dark.observer.initiate(false);
