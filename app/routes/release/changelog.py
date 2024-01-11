
from fastapi import APIRouter

router = APIRouter()

@router.get('/changelog.php')
def changelog():
    # TODO
    return '''
      <html>
        <head>
          <link href="https://web.archive.org/web/20080626041230cs_/http://osu.ppy.sh/release/style.css" rel="stylesheet" type="text/css"/>
        </head>
        <body>
          <img class="floatLeft" src="https://web.archive.org/web/20080626041230im_/http://osu.ppy.sh/release/changelog.png">
          Welcome to the osu! updater!  This program will grab the latest version automatically, and also allow downloading of extras such as skins.<br/>
          &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<b>-<i>peppy</i></b><br/>
          <br/>
          <div class="floatClear">
            <a href="https://web.archive.org/web/20080626041230/http://osu.ppy.sh/">Home</a> |
            <a href="https://web.archive.org/web/20080626041230/http://osu.ppy.sh/index.php?p=faq">FAQ</a> |
            <a href="https://web.archive.org/web/20080626041230/http://osu.ppy.sh/forum/">Forums</a>
          </div>
          <br/><h1>Recent Changes:</h1><div class="date">2008-06-18
          <br/></div>(*) Moving bancho.
          <br/>
          <br/><div class="date">2008-06-17 (b349)
          <br/></div>(+) New match setup/lobby screen graphics.
          <br/>(+) Client-side mods can be set on a per-client basis (currently just NoVideo).
          <br/>(+) Notifications are given when a player joins/quits the game.
          <br/>(+) Users can update a beatmap to the latest from the match setup screen.
          <br/>(+) Multiplayer matches can perform a skip (all players must request this at the beginning of the song).
          <br/>(+) Double-clicking an .osz file or dragging it into the osu! window while at Match Setup will handle the file without leaving the match.
          <br/>(+) Added 'Folder' sort mode for song select.
          <br/>(+) Added '/savelog' command to export chat logs.
          <br/>(+) Multi-channel chat.
          <br/>(*) Bug fixes and many other improvements.
          <br/>
          <br/><div class="date">2008-06-05 (b337)
          <br/></div>(*) Multiplayer bug fixes.
          <br/>
          <br/>
          <div class="date"></div>
        </body>
      </html>'''
