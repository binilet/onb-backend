# Site images

System users manage global images at **Hagere Shops > Site images** in the admin
app. Shop admins/cashiers cannot change global branding. The public player
manifest is provided by bingo-server at GET /api/site-media without authentication.

## Development

Both existing configurations were checked: FastAPI selects `onbingo` on localhost
and bingo-server uses `mongodb://localhost:.../onbingo`. The local `rs0` replica set
supports transactions. No application database URI or credentials were changed.

1. Install onlineBackEnd/requirements.txt in its environment (Pillow with WebP and
   filelock are new). Restart FastAPI from backend/app as usual. Startup creates
   the two indexes on the new siteMedia collection.
2. Default MEDIA_ROOT is `media` relative to the FastAPI working directory. Set
   an absolute path for services so restart/deployment cannot change the location.
   Default MEDIA_BASE_URL is http://localhost:8000/media. Override its port if needed.
3. In development only, FastAPI serves /media/site-media for immediate previews.
   On another device, localhost is not the server: use local HTTPS and set an
   accessible MEDIA_BASE_URL. HTTP is allowed only for loopback development URLs.
4. Build/restart bingo-server. Its existing MONGO_URI selects the shared DB; no
   extra Node credentials or write endpoints are needed.
5. Open Site images as System, upload, position, and activate an image. The player
   refreshes the public manifest on the next app load. Each Node process caches
   it for 60 seconds. Browser/proxy stale-while-revalidate can extend visibility
   delay, so this is not a push update or an exact 60-second guarantee.

## Atlas / VPS

Use site-media.env.example as a configuration reference. Set FastAPI MONGODB_URL
and MONGODB_NAME and Node MONGO_URI to the same Atlas cluster/database. Data is
portable: there is no hostname or connection string embedded in image documents.
Only public image URLs are stored. Atlas network access and database credentials
must permit each backend; use a read-only media reader where deployment supports it.

Moving existing development data to Atlas does not copy it automatically. Use
your normal Mongo migration process, including siteMedia and its indexes. Copy
MEDIA_ROOT/site-media too. Localhost URLs in development records must be migrated
to the production MEDIA_BASE_URL (including variants) or re-upload those images.
Mongo Atlas does not store the image files.

On the VPS, set MEDIA_ROOT=/var/www/hagere-media and an HTTPS MEDIA_BASE_URL. The
FastAPI service user needs write access; nginx needs read/traverse access. Include
deploy/site-media.nginx.conf in the appropriate HTTPS server and adjust the alias
if using a different directory. Add client_max_body_size 2200k to the existing
admin upload proxy location. Validate nginx configuration before reloading it.
Back up media files along with MongoDB. Keep media outside deploy checkout cleanup.

All FastAPI workers writing images MUST use the same MEDIA_ROOT on one VPS/shared
filesystem with working OS file locks. Activation also uses Mongo transactions
and a unique partial index. For multiple separate media hosts, replace the local
file storage/locking layer with coordinated shared/object storage first.

## API

Canonical admin routes follow the spec at /admin/site-media; /api/admin/site-media
is an alias for the existing admin frontend API base. All require a logged-in,
active System user who has completed any required password change.

- POST root: multipart slot, file, alt_en/am/om, focalX/Y, activate.
- GET root: history, optional slot filter.
- PATCH /{id}: alt, focalX/Y, isActive.
- DELETE /{id}: inactive uploads only.
- POST /slots/{slot}/reset: deactivate current image and use player defaults.

Files must be <=2,097,152 bytes (UI label 2 MB). JPEG/PNG/WebP are detected by
decoding, animations are rejected, oriented width must be >=800, either side
<=8000, and decoded pixels <=32 million. EXIF is applied then removed; embedded
ICC colors are converted to sRGB, transparency flattened to white. Widths are
480/800/1200/1600 without upscaling, retaining original width when below 1600.
Quality is 78, method 6; target byte sizes depend on image complexity, not a
guaranteed hard limit on the generated file size.

Re-uploading identical bytes in the same slot reuses one history record and
immutable files, while updating its alt/focal metadata. Other slots have separate
paths. Hash-prefix collisions are rejected. A failed database write removes only
files created by that attempt after checking commit state. When Mongo is
unreachable, possible orphan files are retained rather than deleting valid data;
reconcile them after recovery. File cleanup errors are logged for operations.

## Verification

Backend tests: from backend/app, run `../../env/Scripts/python.exe -m unittest
tests.test_site_media -v` on Windows (normal venv python on Linux). Install httpx
for tests. Tests use generated site_media_test_* databases on localhost and
temporary media directories; application data is untouched.

Node: run `npm run build`, then `node --test tests/site-media.cjs` in bingo-server.
The test process uses its own generated localhost DB and no gameplay background
workers. Frontend: `npm run build`; focused lint on SiteMedia.jsx and its API/nav.

Amharic/Oromo image alt fields are supported. New admin UI translations have
explicit English fallbacks pending human review in src/locales/siteMedia/README.md.
