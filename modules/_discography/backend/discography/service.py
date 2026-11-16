"""All of discography's logic; routers call these with a session and typed arguments.

Slow work goes to kernel jobs.
"""

# TODO, one function per route:
# - list_albums: Published albums, newest first (cursor pagination).
# - get_album: One album with its playable tracks (tracks with no audio are left out).
# - admin_list_albums: Every album with its problems (tracks with no audio, processing).
# - save_album: Create or update an album; sends `version`.
# - upload_track: Upload a master to private storage; queues the job that makes the stream file, duration and peaks.
# - save_track: Title, order, explicit flag, lyrics, or switch the source to a SoundCloud link.
# - delete_track: Remove a track; emits discography.track.deleted.
