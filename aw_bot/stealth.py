"""Making the browser look like a browser somebody is sitting at.

Two different problems get confused with each other, and this module keeps
them apart because the right answer to one is the wrong answer to the other.

    automation artefacts   Things a driven Chrome has that a hand-driven one
                           does not: navigator.webdriver set, the $cdc_ globals
                           ChromeDriver injects, document.hasFocus() returning
                           false because nobody is looking at the window. None
                           of these say anything about the machine. They are
                           pure tells, and scrubbing them is safe everywhere.

    device identity        The GPU string, core count, timezone, canvas hash,
                           user agent. These say which machine this is. They
                           are not tells in themselves -- every real browser
                           has them -- they are only a problem when they
                           contradict each other.

The artefact tier always runs. The identity tier is conditional, and that is
the important part: GoLogin profiles already ship a complete, internally
consistent identity (GPU, cores, screen, timezone, UA and proxy all chosen to
match each other). Layering a second set of values over the top of that does
not make the profile look more human, it makes it look *broken* -- a browser
claiming an Intel Iris on a profile whose UA, proxy geolocation and screen
metrics were built around something else. A contradiction is a far louder
signal than a plain fingerprint, so on GoLogin the identity tier stays off and
the profile speaks for itself. It runs on the SeleniumBase backends, where
nothing else is supplying an identity at all.

`cfg.stealth_fingerprint` overrides that choice ("auto" / "on" / "off") for
when you want to see what the other way looks like.

Everything is injected through Page.addScriptToEvaluateOnNewDocument, so it
lands in every frame -- including the Solix iframe the application actually
lives in -- before any of the page's own script runs. A page that is already
open is too late; call this right after the browser starts.
"""

from .config import RunConfig
from .logs import LOG

# Chrome's magic getParameter() constants for the debug renderer extension.
# 37445 = UNMASKED_VENDOR_WEBGL, 37446 = UNMASKED_RENDERER_WEBGL.
_GPU_VENDOR = "Intel Inc."
_GPU_RENDERER = "Intel(R) Iris(TM) Plus Graphics 640"


# --------------------------------------------------------------------------
# Tier 1: automation artefacts. Safe on every backend.
# --------------------------------------------------------------------------

ARTIFACT_JS = r"""
(function () {
    'use strict';

    var _def = function (obj, prop, getter) {
        try {
            Object.defineProperty(obj, prop, {
                get: getter, configurable: true, enumerable: true
            });
        } catch (e) {}
    };

    /* navigator.webdriver -- the single most-checked flag there is.
       Patched only when it is actually true. Two reasons to leave it alone
       otherwise: a browser that was never launched under automation already
       reports false, and the value to report is `false`, not `undefined`.
       An earlier version returned undefined unconditionally, which is a
       worse answer than the truth -- real Chrome has the property and it
       reads false, so undefined says "someone removed this". */
    try {
        if (navigator.webdriver === true) {
            _def(navigator, 'webdriver', function () { return false; });
        }
    } catch (e) {}

    /* The window.chrome object. Present in every real Chrome, missing or
       hollow under headless. Only filled in where it is actually absent, so a
       profile that already has a real one keeps it. */
    try {
        if (!window.chrome) { window.chrome = {}; }
        if (!window.chrome.runtime) {
            window.chrome.app = {
                isInstalled: false,
                getDetails:     function getDetails()     {},
                getIsInstalled: function getIsInstalled() {},
                InstallState:  { DISABLED:'disabled', INSTALLED:'installed', NOT_INSTALLED:'not_installed' },
                RunningState:  { CANNOT_RUN:'cannot_run', READY_TO_RUN:'ready_to_run', RUNNING:'running' }
            };
            window.chrome.runtime = {
                id: undefined,
                connect:     function connect()     {},
                sendMessage: function sendMessage() {}
            };
            window.chrome.loadTimes = function loadTimes() {
                return {
                    requestTime:            Date.now() / 1000 - 0.5,
                    startLoadTime:          Date.now() / 1000 - 0.4,
                    commitLoadTime:         Date.now() / 1000 - 0.2,
                    finishDocumentLoadTime: 0, finishLoadTime: 0,
                    firstPaintTime:         0, firstPaintAfterLoadTime: 0,
                    navigationType: 'Other', wasFetchedViaSpdy: false,
                    wasNpnNegotiated: false, npnNegotiatedProtocol: 'unknown',
                    wasAlternateProtocolAvailable: false, connectionInfo: 'http/1.1'
                };
            };
            window.chrome.csi = function csi() {
                return { startE: Date.now() - 2000, onloadT: Date.now(), pageT: 1500, tran: 15 };
            };
        }
    } catch (e) {}

    /* navigator.plugins. A real desktop Chrome lists the built-in PDF viewer;
       headless lists nothing. Guarded on length so a profile with its own
       plugin list is left alone. */
    try {
        if (!navigator.plugins || navigator.plugins.length === 0) {
            var _plugins = [
                { name: 'PDF Viewer',               filename: 'internal-pdf-viewer', description: 'Portable Document Format',
                  mt: { type: 'application/pdf',                 suffixes: 'pdf', description: 'Portable Document Format' } },
                { name: 'Chrome PDF Viewer',         filename: 'internal-pdf-viewer', description: '',
                  mt: { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: '' } },
                { name: 'Chromium PDF Viewer',       filename: 'internal-pdf-viewer', description: '',
                  mt: { type: 'application/pdf',                 suffixes: 'pdf', description: '' } },
                { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: '',
                  mt: { type: 'application/pdf',                 suffixes: 'pdf', description: '' } },
                { name: 'WebKit built-in PDF',       filename: 'internal-pdf-viewer', description: '',
                  mt: { type: 'application/pdf',                 suffixes: 'pdf', description: '' } }
            ];
            var _pa = {
                length: _plugins.length,
                item:      function (i) { return this[i]; },
                namedItem: function (n) { for (var i=0;i<_plugins.length;i++) if(_plugins[i].name===n) return _plugins[i]; return null; },
                refresh:   function () {},
                [Symbol.iterator]: function* () { for (var i=0;i<_plugins.length;i++) yield this[i]; }
            };
            var _ma = {
                length: _plugins.length,
                item:      function (i) { return _plugins[i] ? _plugins[i].mt : null; },
                namedItem: function (n) { for (var i=0;i<_plugins.length;i++) if(_plugins[i].mt.type===n) return _plugins[i].mt; return null; },
                [Symbol.iterator]: function* () { for (var i=0;i<_plugins.length;i++) yield _plugins[i].mt; }
            };
            _plugins.forEach(function (p, i) { p.mt.enabledPlugin = p; _pa[i] = p; _ma[i] = p.mt; });
            _def(navigator, 'plugins',   function () { return _pa; });
            _def(navigator, 'mimeTypes', function () { return _ma; });
        }
    } catch (e) {}

    /* Permissions API. The mismatch worth fixing is permissions.query saying
       'denied' for notifications while Notification.permission says
       'default'; a browser where nobody has answered the prompt reports
       'default' from both.

       Only patched when they actually disagree. Overriding query
       unconditionally turns it into an own property of navigator.permissions
       where natively there is none -- the same self-inflicted tell as
       hasFocus above, and measured the same way. */
    try {
        var _notifState = (typeof Notification !== 'undefined')
            ? Notification.permission : 'default';
        if (_notifState !== 'denied' && navigator.permissions && navigator.permissions.query) {
            navigator.permissions.query({ name: 'notifications' }).then(function (r) {
                if (r && r.state === 'denied') {
                    var _oq = navigator.permissions.query.bind(navigator.permissions);
                    Object.defineProperty(navigator.permissions, 'query', {
                        value: function query(p) {
                            if (p && p.name === 'notifications') {
                                return Promise.resolve({ state: _notifState, onchange: null });
                            }
                            return _oq(p);
                        },
                        configurable: true, writable: true
                    });
                }
            }).catch(function () {});
        }
    } catch (e) {}

    try {
        if (typeof Notification !== 'undefined' && Notification.permission === 'denied') {
            _def(Notification, 'permission', function () { return 'default'; });
        }
    } catch (e) {}

    /* Window geometry. Headless reports 0 for the outer dimensions, which no
       window on a screen ever does. */
    try {
        if (!window.outerWidth  || window.outerWidth  === 0)
            _def(window, 'outerWidth',  function () { return window.innerWidth  || screen.width  || 1440; });
        if (!window.outerHeight || window.outerHeight === 0)
            _def(window, 'outerHeight', function () { return (window.innerHeight || screen.height || 1000) + 85; });
    } catch (e) {}

    try {
        if (!screen.orientation) {
            Object.defineProperty(screen, 'orientation', {
                get: function () {
                    return { angle: 0, type: 'landscape-primary', onchange: null,
                             addEventListener: function(){}, removeEventListener: function(){} };
                },
                configurable: true
            });
        }
    } catch (e) {}

    /* The globals ChromeDriver and the older Selenium bridges leave behind.
       Cheap to check for and completely conclusive if found. */
    try { delete window.$cdc_asdjflasutopfhvcZLmcfl_; }   catch (e) {}
    try { delete document.$cdc_asdjflasutopfhvcZLmcfl_; } catch (e) {}
    try { delete window.$wdc_; }                          catch (e) {}
    try { delete window.__webdriver_script_fn; }          catch (e) {}
    try { delete window.__driver_evaluate; }              catch (e) {}
    try { delete window.__webdriver_evaluate; }           catch (e) {}
    try { delete window.__selenium_evaluate; }            catch (e) {}
    try { delete window.__fxdriver_evaluate; }            catch (e) {}
    try { delete window.__driver_unwrapped; }             catch (e) {}
    try { delete window.__webdriver_unwrapped; }          catch (e) {}
    try { delete window.__selenium_unwrapped; }           catch (e) {}
    try { delete window.__fxdriver_unwrapped; }           catch (e) {}
    try { if (window.name && window.name.indexOf('webdriver') !== -1) window.name = ''; } catch (e) {}

    /* document.hasFocus() and the visibility pair are deliberately NOT
       patched any more.

       Natively `hasFocus` lives on Document.prototype and `document` has no
       own property for it at all. Overriding it creates one, and
       `Object.getOwnPropertyDescriptor(document, 'hasFocus')` then returns a
       descriptor where a clean browser returns undefined -- so the patch is
       more visible than the thing it was hiding. Measured on this project's
       own profiles: with the patch, that descriptor is present; without it,
       absent, and everything else reads identically.

       The honest fix for an unfocused window is to focus the window, which
       the run already does before waiting on Turnstile (real_input.
       focus_window). A page that says it is focused while the window plainly
       is not is a lie a browser can be caught in; a window that is actually
       in front needs no lie. */

    /* Everything above replaces a native function with a plain JS one, and
       calling toString() on those prints the source instead of the
       '[native code]' stub. Sensors probe exactly that, so the patched
       functions are registered here and answer the way natives do. */
    try {
        var _origFnToStr = Function.prototype.toString;
        var _fakeNatives = new WeakSet();
        Object.defineProperty(Function.prototype, 'toString', {
            value: function toString() {
                if (_fakeNatives.has(this)) {
                    return 'function ' + (this.name || '') + '() { [native code] }';
                }
                return _origFnToStr.call(this);
            },
            configurable: true, writable: true
        });
        window.__awMarkNative = function (fn) { try { _fakeNatives.add(fn); } catch (e) {} };
        _fakeNatives.add(Function.prototype.toString);
        _fakeNatives.add(document.hasFocus);
        try { _fakeNatives.add(navigator.permissions.query); } catch (e) {}
    } catch (e) {}
})();
"""


# --------------------------------------------------------------------------
# Tier 2: device identity. Only where nothing else is supplying one.
# --------------------------------------------------------------------------

FINGERPRINT_JS = r"""
(function () {
    'use strict';

    var _def = function (obj, prop, getter) {
        try {
            Object.defineProperty(obj, prop, {
                get: getter, configurable: true, enumerable: true
            });
        } catch (e) {}
    };
    var _markNative = function (fn) {
        try { if (window.__awMarkNative) window.__awMarkNative(fn); } catch (e) {}
    };

    var _GPU_VENDOR   = '__GPU_VENDOR__';
    var _GPU_RENDERER = '__GPU_RENDERER__';

    /* Core navigator values, kept as one consistent Windows desktop. */
    _def(navigator, 'platform',            function () { return 'Win32'; });
    _def(navigator, 'language',            function () { return 'en-US'; });
    _def(navigator, 'languages',           function () { return Object.freeze(['en-US', 'en']); });
    _def(navigator, 'hardwareConcurrency', function () { return 8; });
    _def(navigator, 'deviceMemory',        function () { return 8; });
    _def(navigator, 'doNotTrack',          function () { return null; });
    _def(navigator, 'maxTouchPoints',      function () { return 0; });
    _def(navigator, 'vendor',              function () { return 'Google Inc.'; });
    _def(navigator, 'vendorSub',           function () { return ''; });
    _def(navigator, 'productSub',          function () { return '20030107'; });
    _def(screen,     'colorDepth',         function () { return 24; });
    _def(screen,     'pixelDepth',         function () { return 24; });

    /* Patch the prototype too: a WorkerNavigator inherits from Navigator, so
       without this a worker reports the machine's real core count while the
       main thread reports 8, and the two disagreeing is the tell. */
    try { Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', { get: function(){return 8;}, configurable:true, enumerable:true }); } catch (e) {}
    try { Object.defineProperty(Navigator.prototype, 'deviceMemory',        { get: function(){return 8;}, configurable:true, enumerable:true }); } catch (e) {}

    /* WebGL vendor/renderer, three ways, because which one works depends on
       the Chrome build: the prototype method, the debug extension that
       exposes it, and each context as it is created. The real getParameter is
       captured before the override so the fallback never re-enters this. */
    try {
        var _patchWGLClass = function (Ctx) {
            if (!Ctx || !Ctx.prototype) return;
            var _origGP = Ctx.prototype.getParameter;
            try {
                Object.defineProperty(Ctx.prototype, 'getParameter', {
                    value: function getParameter(p) {
                        if (p === 37445) return _GPU_VENDOR;
                        if (p === 37446) return _GPU_RENDERER;
                        return _origGP.call(this, p);
                    },
                    writable: true, configurable: true
                });
                _markNative(Ctx.prototype.getParameter);
            } catch (e) {}
            var _origGE = Ctx.prototype.getExtension;
            try {
                Object.defineProperty(Ctx.prototype, 'getExtension', {
                    value: function getExtension(name) {
                        if (name === 'WEBGL_debug_renderer_info') return null;
                        return _origGE.call(this, name);
                    },
                    writable: true, configurable: true
                });
                _markNative(Ctx.prototype.getExtension);
            } catch (e) {}
            var _origGSE = Ctx.prototype.getSupportedExtensions;
            if (_origGSE) {
                try {
                    Object.defineProperty(Ctx.prototype, 'getSupportedExtensions', {
                        value: function getSupportedExtensions() {
                            var list = _origGSE.call(this);
                            return list ? list.filter(function (e) { return e !== 'WEBGL_debug_renderer_info'; }) : list;
                        },
                        writable: true, configurable: true
                    });
                } catch (e) {}
            }
        };
        _patchWGLClass(window.WebGLRenderingContext);
        _patchWGLClass(window.WebGL2RenderingContext);

        var _origGetCtx = HTMLCanvasElement.prototype.getContext;
        Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
            value: function getContext(type, attrs) {
                var ctx = _origGetCtx.apply(this, arguments);
                if (ctx && (type === 'webgl' || type === 'experimental-webgl' || type === 'webgl2')) {
                    try {
                        var _ctxGP = ctx.getParameter;
                        Object.defineProperty(ctx, 'getParameter', {
                            value: function getParameter(p) {
                                if (p === 37445) return _GPU_VENDOR;
                                if (p === 37446) return _GPU_RENDERER;
                                return _ctxGP.call(ctx, p);
                            },
                            configurable: true, writable: true
                        });
                    } catch (e) {}
                    try {
                        var _ctxGE = ctx.getExtension;
                        Object.defineProperty(ctx, 'getExtension', {
                            value: function getExtension(name) {
                                if (name === 'WEBGL_debug_renderer_info') return null;
                                return _ctxGE.call(ctx, name);
                            },
                            configurable: true, writable: true
                        });
                    } catch (e) {}
                }
                return ctx;
            },
            writable: true, configurable: true
        });
        _markNative(HTMLCanvasElement.prototype.getContext);
    } catch (e) {}

    /* navigator.userAgentData. The CDP override below sets the low-entropy
       brands at the network layer, but a page can read the JS object before
       any request goes out, and getHighEntropyValues() answers straight from
       the renderer whatever CDP was told. Both have to be patched here or the
       two sources disagree. */
    try {
        if (navigator.userAgentData) {
            var _uaBrands = [
                { brand: 'Not=A?Brand',   version: '24'                },
                { brand: 'Chromium',      version: '__STEALTH_MAJOR__' },
                { brand: 'Google Chrome', version: '__STEALTH_MAJOR__' }
            ];
            Object.defineProperty(navigator.userAgentData, 'brands', {
                get: function () { return _uaBrands.map(function (b) { return { brand: b.brand, version: b.version }; }); },
                configurable: true, enumerable: true
            });
            Object.defineProperty(navigator.userAgentData, 'mobile', {
                get: function () { return false; }, configurable: true, enumerable: true
            });
            Object.defineProperty(navigator.userAgentData, 'platform', {
                get: function () { return 'Windows'; }, configurable: true, enumerable: true
            });

            if (navigator.userAgentData.getHighEntropyValues) {
                var _origGHEV = navigator.userAgentData.getHighEntropyValues.bind(navigator.userAgentData);
                Object.defineProperty(navigator.userAgentData, 'getHighEntropyValues', {
                    value: function getHighEntropyValues(hints) {
                        return _origGHEV(hints).then(function (r) {
                            /* The UADataValues result is frozen: clone before touching it. */
                            var result = {};
                            try { Object.assign(result, r); } catch (e) { result = r; }
                            if (hints.indexOf('platformVersion') !== -1) result.platformVersion = '10.0.0';
                            if (hints.indexOf('architecture')    !== -1) result.architecture    = 'x86';
                            if (hints.indexOf('bitness')         !== -1) result.bitness         = '64';
                            if (hints.indexOf('model')           !== -1) result.model           = '';
                            if (hints.indexOf('wow64')           !== -1) result.wow64           = false;
                            if (hints.indexOf('uaFullVersion')   !== -1) result.uaFullVersion   = '__STEALTH_FULL_VER__';
                            if (hints.indexOf('fullVersionList') !== -1) result.fullVersionList = [
                                { brand: 'Not=A?Brand',   version: '24.0.0.0'             },
                                { brand: 'Chromium',      version: '__STEALTH_FULL_VER__' },
                                { brand: 'Google Chrome', version: '__STEALTH_FULL_VER__' }
                            ];
                            return result;
                        });
                    },
                    configurable: true, writable: true
                });
            }
        }
    } catch (e) {}

    /* Workers get their own global scope, and addScriptToEvaluateOnNewDocument
       does not reach it -- so a sensor that asks a worker for the GPU string
       gets the real one. Wrap Worker construction and importScripts() a patch
       ahead of the real script. Module workers cannot be wrapped this way and
       are left alone. */
    try {
        var _workerPatch = '(function(){'
            + 'try{'
            +   '["WebGLRenderingContext","WebGL2RenderingContext"].forEach(function(n){'
            +     'var C=self[n];if(!C||!C.prototype)return;'
            +     'var oGP=C.prototype.getParameter;'
            +     'C.prototype.getParameter=function(p){if(p===37445)return"' + _GPU_VENDOR + '";if(p===37446)return"' + _GPU_RENDERER + '";return oGP.call(this,p);};'
            +     'var oGE=C.prototype.getExtension;'
            +     'C.prototype.getExtension=function(n){if(n==="WEBGL_debug_renderer_info")return null;return oGE.call(this,n);};'
            +   '});'
            + '}catch(e){}'
            + 'try{if(typeof OffscreenCanvas!=="undefined"){'
            +   'var oOC=OffscreenCanvas.prototype.getContext;'
            +   'OffscreenCanvas.prototype.getContext=function(t,a){'
            +     'var c=oOC.apply(this,arguments);'
            +     'if(c&&(t==="webgl"||t==="webgl2")){try{Object.defineProperty(c,"getParameter",{value:function(p){if(p===37445)return"' + _GPU_VENDOR + '";if(p===37446)return"' + _GPU_RENDERER + '";return WebGLRenderingContext.prototype.getParameter.call(this,p);},configurable:true,writable:true});}catch(e){}}'
            +     'return c;'
            +   '};'
            + '}}catch(e){}'
            + 'try{Object.defineProperty(self.navigator,"hardwareConcurrency",{get:function(){return 8;},configurable:true});}catch(e){}'
            + 'try{Object.defineProperty(self.navigator,"deviceMemory",{get:function(){return 8;},configurable:true});}catch(e){}'
            + 'try{if(typeof Notification!=="undefined")Object.defineProperty(Notification,"permission",{get:function(){return"default";},configurable:true});}catch(e){}'
            + '})();';
        var _OrigWorker = window.Worker;
        window.Worker = function Worker(url, options) {
            try {
                if (!(options && options.type === 'module')) {
                    var scriptUrl = (url instanceof URL) ? url.href : String(url);
                    var patchUrl  = URL.createObjectURL(new Blob([_workerPatch], { type: 'application/javascript' }));
                    var wrapSrc   = 'importScripts(' + JSON.stringify(patchUrl) + ',' + JSON.stringify(scriptUrl) + ');';
                    url = URL.createObjectURL(new Blob([wrapSrc], { type: 'application/javascript' }));
                }
            } catch (e) {}
            return new _OrigWorker(url, options);
        };
        window.Worker.prototype = _OrigWorker.prototype;
    } catch (e) {}

    /* Network Information and Battery. Both are missing under automation and
       present on a real desktop Chrome. */
    try {
        if (!navigator.connection) {
            _def(navigator, 'connection', function () {
                return { downlink: 10, downlinkMax: 100, effectiveType: '4g', onchange: null,
                         rtt: 50, saveData: false,
                         addEventListener: function () {}, removeEventListener: function () {} };
            });
        } else if (navigator.connection.downlinkMax === undefined) {
            Object.defineProperty(navigator.connection, 'downlinkMax',
                { get: function () { return 100; }, configurable: true });
        }
    } catch (e) {}

    try {
        navigator.getBattery = function getBattery() {
            return Promise.resolve({
                charging: true, chargingTime: 0, dischargingTime: Infinity, level: 1.0,
                onchargingchange: null, onchargingtimechange: null,
                ondischargingtimechange: null, onlevelchange: null,
                addEventListener: function () {}, removeEventListener: function () {}
            });
        };
        _markNative(navigator.getBattery);
    } catch (e) {}

    /* WebRTC. ICE candidate gathering reports the host's real addresses
       regardless of the proxy, so a page can read the true IP straight past
       it. Relay-only with no servers configured means nothing is gathered. */
    try {
        var _OrigRTCPC = window.RTCPeerConnection;
        if (_OrigRTCPC) {
            window.RTCPeerConnection = function RTCPeerConnection(config, constraints) {
                var safe = Object.assign({}, config || {});
                safe.iceServers         = [];
                safe.iceTransportPolicy = 'relay';
                return new _OrigRTCPC(safe, constraints);
            };
            window.RTCPeerConnection.prototype = _OrigRTCPC.prototype;
            if (_OrigRTCPC.generateCertificate) {
                window.RTCPeerConnection.generateCertificate = _OrigRTCPC.generateCertificate;
            }
            if (window.webkitRTCPeerConnection) {
                window.webkitRTCPeerConnection = window.RTCPeerConnection;
            }
        }
    } catch (e) {}

    /* Canvas and audio readback noise, a constant per session. A canvas hash
       that is byte-identical across every run on every machine is what marks
       a fleet as one fleet; a small constant offset makes each session its
       own device while staying stable within the session, which is how a real
       device behaves. Chosen once here rather than per call for that reason:
       noise that changes between two reads of the same canvas is itself
       detectable. */
    try {
        var _c2dNoise = Math.floor(Math.random() * 5) - 2;
        var _origGID = CanvasRenderingContext2D.prototype.getImageData;
        Object.defineProperty(CanvasRenderingContext2D.prototype, 'getImageData', {
            value: function getImageData(x, y, w, h) {
                var d = _origGID.call(this, x, y, w, h);
                for (var i = 0; i < d.data.length; i += 4) {
                    d.data[i]   = Math.max(0, Math.min(255, d.data[i]   + _c2dNoise));
                    d.data[i+1] = Math.max(0, Math.min(255, d.data[i+1] + _c2dNoise));
                    d.data[i+2] = Math.max(0, Math.min(255, d.data[i+2] + _c2dNoise));
                }
                return d;
            },
            configurable: true, writable: true
        });
        _markNative(CanvasRenderingContext2D.prototype.getImageData);
    } catch (e) {}

    try {
        var _ACtxCls = window.AudioContext || window.webkitAudioContext;
        if (_ACtxCls) {
            var _origCAn = _ACtxCls.prototype.createAnalyser;
            Object.defineProperty(_ACtxCls.prototype, 'createAnalyser', {
                value: function createAnalyser() {
                    var an = _origCAn.apply(this, arguments);
                    var _gf = an.getFloatFrequencyData.bind(an);
                    var _gb = an.getByteFrequencyData.bind(an);
                    an.getFloatFrequencyData = function (arr) {
                        _gf(arr);
                        for (var i = 0; i < arr.length; i++) arr[i] += (Math.random() - 0.5) * 1e-4;
                    };
                    an.getByteFrequencyData = function (arr) {
                        _gb(arr);
                        for (var i = 0; i < arr.length; i++)
                            arr[i] = Math.max(0, Math.min(255, arr[i] + (Math.random() < 0.5 ? 1 : -1)));
                    };
                    return an;
                },
                configurable: true, writable: true
            });
        }
    } catch (e) {}
})();
"""


def apply(sb, cfg: RunConfig, backend: str = "") -> None:
    """Install the stealth layer on a freshly started browser.

    Call before the first navigation: the scripts run on new documents, so
    anything already loaded has had its chance to look.
    """
    if not getattr(cfg, "stealth", True):
        LOG.info("Stealth layer off (cfg.stealth)")
        return

    driver = getattr(sb, "driver", sb)
    if not hasattr(driver, "execute_cdp_cmd"):
        # A remote grid speaks plain WebDriver and offers no CDP endpoint, so
        # there is nowhere to install this. Worth saying out loud rather than
        # failing quietly, since it is exactly the backend that has no other
        # anti-detection either.
        LOG.warning(
            "Stealth needs a CDP connection and this driver has none (remote "
            "grid?). The browser goes to the site unpatched."
        )
        return

    applied = []
    if wants_artifacts(cfg, backend):
        if _inject(driver, ARTIFACT_JS, "artifact"):
            applied.append("automation artefacts")
    else:
        LOG.info(
            "Automation artefacts left alone: a %s profile is a normally "
            "launched browser and already reports clean", backend or cfg.browser_backend,
        )

    if wants_fingerprint(cfg, backend):
        ua, major, full = _user_agent(driver)
        script = (
            FINGERPRINT_JS
            .replace("__GPU_VENDOR__", _GPU_VENDOR)
            .replace("__GPU_RENDERER__", _GPU_RENDERER)
            .replace("__STEALTH_MAJOR__", major)
            .replace("__STEALTH_FULL_VER__", full)
        )
        if _inject(driver, script, "fingerprint"):
            applied.append("device identity")
        _cdp_identity(driver, ua, major, full)
    else:
        LOG.info(
            "Device identity left to the %s profile; only automation "
            "artefacts patched", backend or cfg.browser_backend,
        )

    if applied:
        LOG.info("Stealth applied: %s", ", ".join(applied))


def wants_artifacts(cfg: RunConfig, backend: str = "") -> bool:
    """Whether the artefact patches are worth applying to this browser.

    Off for GoLogin, and that is a measured decision rather than a cautious
    one. Orbita is a real browser that GoLogin starts normally; we attach to
    its DevTools port instead of launching it with --enable-automation, so
    nothing sets the usual tells in the first place. Probed side by side on
    fresh profiles, patched against unpatched:

        navigator.webdriver     undefined   vs  false      <- false is correct
        document.hasFocus desc  present     vs  absent     <- present is the tell
        permissions.query desc  present     vs  absent     <- same
        $cdc_ globals           0           vs  0
        navigator.plugins       5           vs  5

    Everything the patches were there to fix was already right, and each
    patch added something a page can check for. On a browser that is clean,
    anti-detection is net negative: the only thing left to detect is the
    anti-detection.

    Still on for the SeleniumBase backends, where Chrome *is* launched under
    automation and those tells are real.
    """
    mode = (getattr(cfg, "stealth_artifacts", "auto") or "auto").lower()
    if mode == "on":
        return True
    if mode == "off":
        return False
    return (backend or cfg.browser_backend or "").lower() != "gologin"


def wants_fingerprint(cfg: RunConfig, backend: str = "") -> bool:
    """Whether to impose an identity, or let the profile supply its own."""
    mode = (getattr(cfg, "stealth_fingerprint", "auto") or "auto").lower()
    if mode == "on":
        return True
    if mode == "off":
        return False
    # auto: GoLogin brings a complete, self-consistent fingerprint of its own
    # and a second one layered over it only creates contradictions.
    return (backend or cfg.browser_backend or "").lower() != "gologin"


def _inject(driver, script: str, label: str) -> bool:
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": script})
        return True
    except Exception as exc:
        LOG.warning("Could not install the %s patches: %s", label, exc)
        return False


def _user_agent(driver) -> tuple[str, str, str]:
    """A UA string built from the Chrome that actually launched.

    Inventing a version here is how the UA ends up claiming one Chrome while
    the binary behaves like another -- a mismatch anything checking the two
    together will spot.
    """
    caps = getattr(driver, "capabilities", {}) or {}
    raw = (caps.get("browserVersion") or caps.get("version") or "").strip()
    full = raw or "131.0.0.0"
    major = full.split(".")[0]
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{full} Safari/537.36"
    )
    return ua, major, full


def _cdp_identity(driver, ua: str, major: str, full: str) -> None:
    """The half of the identity that only CDP can set.

    Timezone and locale go through CDP rather than JS because Intl and
    Date read them from the renderer, below anything a page script can patch --
    and a browser whose UA says Windows/en-US while Date reports a different
    zone is a browser with something to hide.
    """
    overrides = (
        ("Network.setUserAgentOverride", {
            "userAgent": ua,
            "acceptLanguage": "en-US,en;q=0.9",
            "platform": "Win32",
            "userAgentMetadata": {
                "brands": [
                    {"brand": "Not=A?Brand", "version": "24"},
                    {"brand": "Chromium", "version": major},
                    {"brand": "Google Chrome", "version": major},
                ],
                "fullVersion": full,
                "platform": "Windows",
                "platformVersion": "10.0.0",
                "architecture": "x86",
                "model": "",
                "mobile": False,
                "bitness": "64",
                "wow64": False,
            },
        }),
        ("Emulation.setTimezoneOverride", {"timezoneId": "America/Los_Angeles"}),
        ("Emulation.setLocaleOverride", {"locale": "en-US"}),
        ("Emulation.setHardwareConcurrencyOverride", {"hardwareConcurrency": 8}),
    )

    for command, params in overrides:
        try:
            driver.execute_cdp_cmd(command, params)
        except Exception as exc:
            # Emulation.* comes and goes between Chrome versions; the JS tier
            # already covers most of what these set, so a miss is survivable.
            LOG.debug("CDP %s not accepted: %s", command, exc)
