<!-- Copied from VM Website/design/specs/videos-player.md on 2026-11-15, synced 2026-11-18. The VM Website copy is the source; update both. -->

# Videos section: YouTube playlist player (spec for the real site)

Designed on the working canvas (`design/site/Main.dc.html`, section `#videos`). This is how the production component should behave.

## Data
Managed in Admin › Players › Videos (see `players-admin.md` for the data model, API and admin screens).

A list of `{ url, title, poster? }`. `url` accepts any YouTube link: `youtu.be/ID`, `youtube.com/watch?v=ID` (extra params fine), `/shorts/ID`, `/embed/ID`, `/live/ID`, `m.youtube.com`, or a bare 11-character ID. Parse with:

```js
/(?:youtu\.be\/|youtube(?:-nocookie)?\.com\/(?:watch\?(?:[^#]*&)?v=|embed\/|shorts\/|live\/|v\/))([A-Za-z0-9_-]{11})/
```
Thumbnails: `https://i.ytimg.com/vi/<id>/hqdefault.jpg`, layered over the optional `poster` art. Later this list can come from the admin backend or the YouTube Data API (channel uploads).

## Layout
Panel with a 16:9 stage plus a control bar on the left and a 380px playlist on the right. The playlist is pinned to the stage's height and scrolls, so the player never changes size. Under 980px it stacks and the playlist is 420px tall. Under 600px the poster caption hides and the control bar puts the title on its own line.

## Behavior
- **Facade first.** Show the poster, title and a big play button. Load the iframe only on click (`youtube-nocookie.com/embed/<id>?autoplay=1&rel=0&playsinline=1`). Faster pages, no YouTube cookies until a visitor plays.
- **Rolls through the list.** Use the official IFrame API (`https://www.youtube.com/iframe_api`). On `onStateChange` ENDED with Autoplay on, advance to the next item with `loadVideoById` and move the highlight. The canvas prototype uses the simpler `&playlist=` param, which advances but can't move the highlight.
- Clicking a playlist row plays it. Prev and next wrap around. Autoplay is a switch (`aria-pressed`), on by default. Toggling it never restarts the current video.
- **One thing plays at a time.** Starting a video pauses the album deck and the now-playing bar, and starting audio stops the video.
- Current row: `aria-current="true"`, orange ring and tint, animated equalizer while playing (still under reduced motion).

## The Videos page
`/videos` (`design/site/Videos.dc.html`, owner, 2026-11-17) uses this same player at the top, playing every video in the list, then shows the whole list as cards with filters by kind (All, Music videos, Rap battles, Poetry; suggested names). Picking a card plays it in the player and scrolls up to it (no smooth scroll under reduced motion); the playing card gets an orange ring and a "Now playing" label. The filters change the cards only, never the player's playlist. The homepage's section header has an "All videos" link here.

## Canvas note
claude.ai artifacts block iframes from other sites, so in the canvas the stage shows "Plays right here on the live site" with a Watch on YouTube link instead of the player. The real site has no such check.
