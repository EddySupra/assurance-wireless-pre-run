DROP CHROME EXTENSIONS IN THIS FOLDER
=====================================

Anything you put here loads into the bot's browser on every run.
There is nothing to configure. Just run the bot like normal.

What you can drop here:
  - a .zip or .crx file of an extension
  - an extension's folder (the one with manifest.json in it)


EASIEST WAY: copy an extension you already have in Chrome
---------------------------------------------------------
1. In your normal Chrome, install the extension from the Chrome Web Store.
2. Go to chrome://extensions, turn on "Developer mode" (top right),
   and copy the extension's ID (a long string of letters).
3. Press Win+R, paste this, and press Enter:
       %LOCALAPPDATA%\Google\Chrome\User Data\Default\Extensions
4. Copy the folder named after that ID into this folder.

Then run the bot. The log says "Loading 1 extension(s) into every browser".


EXTENSIONS THAT NEED AN API KEY (CapSolver)
-------------------------------------------
Put the key in the project's .env file:
    CAPSOLVER_API_KEY=CAP-your-key-here
Every browser then starts with the key already filled in.


Good to know
------------
- To stop using one, delete it from this folder.
- Works with the GoLogin backend (the default) and the local ones.
  It does NOT work with --backend browserless or remote.
- Ad blockers and anything that changes web pages can make the site
  refuse the run. If runs start failing, remove the extension first.
  
c:\Users\casas\AppData\Local\Google\Chrome\User Data\Default\Extensions\pgojnojmmhpofjgdmaebadhbocahppod