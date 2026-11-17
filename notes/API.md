# Notes API

Base path: `/api/v1/notes/`. JSON endpoints return `Cache-Control: no-store`. Mutations require `Authorization: Bearer <access_token>` for an active, verified account. Public reads work without a token; supplying an invalid token returns `401`.

## Explore and reading

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Explore published notes |
| `GET /<note_id>/` | Read note metadata, publisher, links, likes, and PDF information |
| `GET /<note_id>/pdf/` | Stream the PDF inline; `?download=true` returns it as an attachment |
| `GET /<note_id>/comments/` | Read note discussion |

Explore accepts `q`, `university`, `department`, `subject`, `course`, `publisher`, and `kind`. Academic and publisher filters use UUIDs. `q` searches title and descriptions. `order=recent` is the default; `order=liked` sorts by like count. Responses have `count`, `limit`, `offset`, and `results`; `limit` defaults to 30 and may be 1–100. Public responses include only published notes with an available PDF, an active verified publisher, no deletion, and no moderation hold. Drafts and archived notes are accessible only to their owner through owner endpoints.

## Authoring

| Endpoint | Purpose |
| --- | --- |
| `GET me/` | List your non-deleted notes, including drafts and archived notes |
| `POST me/` | Create a draft |
| `GET me/<note_id>/` | Read your note, including private drafts |
| `PATCH me/<note_id>/` | Edit draft or published metadata |
| `DELETE me/<note_id>/` | Soft-delete your note |
| `PUT me/<note_id>/resources/` | Atomically replace zero to five ordered links |
| `POST me/<note_id>/pdf/` | Upload or replace a draft PDF using multipart field `pdf` |
| `DELETE me/<note_id>/pdf/` | Remove a draft PDF |
| `POST me/<note_id>/publish/` | Publish a draft with a readable PDF |
| `POST me/<note_id>/archive/` | Archive a published note |

Creating a draft requires `department_id`, `subject_id`, `title`, and `short_description`. Optional fields are `course_id`, `kind`, and `detail_description`. Department, subject, and optional course must be active; a course must match the note's department and subject. An inactive academic reference prevents publication. Metadata and resource edits are unavailable after archiving or during a moderation hold. Only an unrestricted draft may change its PDF. `pending_review` exists in the schema but is reserved until a review workflow is defined.

Resource replacement takes `{ "resources": [{ "label": "...", "url": "https://..." }] }`. Links must use HTTP or HTTPS without embedded credentials. Their positions are 1–5 and are also limited by database constraints. PDF uploads must be unencrypted, readable, 1–500 pages, and no larger than 20 MB. A PDF's internal storage key and checksum never appear in API responses. File cleanup happens after successful database changes.

## Engagement and discussion

| Endpoint | Purpose |
| --- | --- |
| `POST /<note_id>/like/` and `DELETE /<note_id>/like/` | Like or unlike a published note |
| `POST /<note_id>/save/` and `DELETE /<note_id>/save/` | Save or unsave a note |
| `GET me/saved/` | List your saved notes |
| `POST /<note_id>/comments/` | Comment with `body` and optional `parent_comment_id` |
| `PATCH /<note_id>/comments/<comment_id>/` | Edit your comment body |
| `DELETE /<note_id>/comments/<comment_id>/` | Soft-delete your comment |

Like and save operations are idempotent. A saved note that is later hidden or archived stays in the saved list as `available: false`, without note details; it can still be unsaved. Comments can reply only to a comment on the same note. Deleted or moderated comments retain their ID and parent link as placeholders, with no body or author in public responses. Comments are paginated with `limit` and `offset`.

Errors use `{ "error": "..." }` with `400` for invalid input, `401` for missing or invalid authentication, `404` for unavailable or non-owned records, `409` for invalid state changes, and `413` for oversized uploads.
