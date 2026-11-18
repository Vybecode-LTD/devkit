<!-- Copied from VM Website/design/specs/players-admin.md on 2026-11-15, synced 2026-11-18. The VM Website copy is the source; update both. -->

# Players admin: Spotlight, Releases and Videos (spec for the real site)

The homepage has three players. Each one gets its own place in the admin backend, so the team decides what plays in each, in what order, and when. Modules: **`featured`** (slots and placements, new), **`discography`** (the music library, new), **`audio-player`** (playback, new) and **`embeds`** (the YouTube player). Plan: `backend-plan.md`.

| Player | Where on the homepage | Holds | Prototype data (`design/generators/build_final.py`) |
| --- | --- | --- | --- |
| **Spotlight** | The bar under the hero, labelled "Spotlight single". Also drives the hero's "Play …" button | One or more **tracks**, in order (prev and next move through them) | `SPOTLIGHT` |
| **Releases** | The album deck in the Releases section | **Albums**, in order. Each album's track order is set on the album itself | `ALBUMS` |
| **Videos** | The YouTube playlist player in the Videos section | **YouTube links**, in order | `VIDEOS` (see `videos-player.md`) |

## Library vs placement

There's one library, and the players only point into it. Uploading a track never puts it on the homepage. Placing it in a player does.

- **Library:** albums and tracks, in `discography` (Admin › Music).
- **Placements:** an ordered list per slot, in `featured` (Admin › Homepage › Players). A placement points at a library item, or holds a plain link (videos).

## Data model (Postgres; each module has its own Alembic branch)

```
discography_album   id, slug, title, year, artist_line, credit, cover_url, screen_url, screen_focus, status
discography_track   id, album_id (null for a loose single), position, title,
                    source ('upload' | 'soundcloud'), file_key (private master), stream_key (public stream file),
                    external_url, duration_ms, peaks (jsonb), explicit, status

featured_slot       key PK ('spotlight' | 'releases' | 'videos' on this site), label, accepts (e.g. ["discography.track"] or ["link"]), settings (jsonb)
featured_placement  id, slot_key FK, position, kind ('item' | 'link'),
                    ref_module, ref_type, ref_id        -- for an item, such as discography / track / <uuid>
                    url, title, poster_url              -- for a link, such as a YouTube video
                    video_kind (null)                   -- a video's kind, the Videos page's filters: 'music-video' | 'rap-battle' | 'poetry' (confirmed by the owner, 2026-11-18)
                    starts_at (null), ends_at (null)
                    unique (slot_key, position)
```

`featured` has no foreign keys into `discography` (SPEC 10). It stores the ids, and when it hears `discography.track.deleted` or `discography.album.deleted` it drops the matching placements. Slots are declared by the site in seed data, so another site can have `featured-products` or `homepage-posts` instead.

**"At any given time":** each placement has optional `starts_at` and `ends_at`. Only placements that are live right now are served. For example, you can schedule a new spotlight single to go live at midnight on release day and swap out the old one automatically. With no dates set, a placement is simply live.

## API (SPEC 7: routes at `/api/<id>`, admin under `/api/<id>/admin`)

- `GET /api/featured/slots/{key}` (public): the live placements in order.
- `GET /api/site/home` (public; site code in `backend/app/site/`): the whole homepage in one cached response. It resolves the spotlight and releases references through `discography`'s `public.py` (titles, covers, stream URLs, peaks) and passes the video links through. It's cached for 60 s and cleared when `featured.placement.changed` or `discography.*` events arrive.
- `GET` and `PUT /api/featured/admin/slots/{key}` (`featured.placement.manage`): read, or replace the whole ordered list in one save. Each save sends a `version` (SaveConflict), checks every reference against the slot's `accepts` list, and is written to the audit log.
- `discography` admin routes: album CRUD, track upload (`POST /api/discography/admin/tracks`; a job makes the stream file, duration and peaks), and SoundCloud links. When a YouTube link is pasted, `featured` pre-fills the title from YouTube's oEmbed (outbound call through the kernel's SSRF guard).

## Admin screens: Admin › Homepage › Players

One page, three tabs, the same layout on each. It's drawn on the canvas's **Admin** page.

1. **Spotlight:** "Add track" opens a picker over the library (search, album filter). Drag to reorder, remove, set optional start and end dates. The first live track is what the hero's play button names.
2. **Releases:** "Add album" picker, drag to reorder. Each row links to the album editor for its track order and credits.
3. **Videos:** paste one or several YouTube links at once; each is parsed and its title fetched. Edit titles, set an optional poster and kind, drag to reorder. The same list feeds the homepage's Videos section and the Videos page (`/videos`, owner, 2026-11-17), which reads `GET /api/featured/slots/videos` and filters by kind. Each row's Kind menu is on the Players board's Videos tab (`design/site/AdminPlayers.dc.html`).

Every tab shows a **Now playing** strip (what's live this minute), an **Up next** list (scheduled items), and a live preview of the real homepage component. Save puts it live. There's no separate publish step, but the audit log can restore any earlier version.

## Front end

- The homepage reads `/api/site/home` once (TanStack Query, through the generated client).
- **One thing plays at a time:** `audio-player` owns a small shared store. Starting the spotlight pauses the deck and stops the video, starting the deck pauses the spotlight and stops the video, and starting a video pauses both. The prototype logic already behaves this way.
- **Empty states:** with no live spotlight, the label and bar are hidden and the hero button falls back to "Meet the collective". With no albums, Releases says new music is coming. With no videos, the Videos section and its nav link are hidden.

## Backend settings (set in the admin, not decided up front)

These three are configured by the team in the backend at any time. None of them is a launch-day decision.

- **What's in the spotlight:** Admin › Homepage › Players › Spotlight. The canvas uses sample picks (the Catalyst album, then the first two Unified Vibration tracks) only as placeholders.
- **Where each track's audio comes from:** chosen per track in Admin › Music, with a site default in Admin › Settings › Music.
  - *Upload:* the master stays private in R2, and a job makes a public stream file, the duration and the waveform peaks. It plays in the custom player with the real waveform.
  - *SoundCloud:* a link (Catalyst is on SoundCloud as petroDESTROYS). It plays through SoundCloud's widget API behind the same custom controls, with a generic waveform when the real one isn't available.
- **Who can change the players:** each module declares its permissions in `module.json`, and the kernel's roles service grants them (Admin › People and access › Roles). The owner can change who has what at any time.

| Permission | Lets you | Default roles |
| --- | --- | --- |
| `featured.placement.manage` | Place, order and schedule items in Spotlight, Releases and Videos | admin, editor |
| `discography.release.manage` | Albums, tracks, uploads and credits in the library | admin, editor |
| `discography.settings.manage` | The site default for audio source | admin |
