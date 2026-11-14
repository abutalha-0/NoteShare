# Explore Notes schema decisions

The authoritative combined diagram is [fieldnotes.dbml](./fieldnotes.dbml). It contains the full planned product schema. This document records Explore Notes rules that the DBML diagram alone does not enforce.

## Classification

- A note has one academic department and one subject. Its university is derived from `academic_departments.university_id`; do not add a second university ID to `notes`.
- `subjects` are shared concepts such as Data Structures or Linear Algebra. `courses` are institution-specific offerings such as CS101 and belong to one department and one subject. A note may omit `course_id`.
- If a note has a course, its `course_id` must point to the same department and subject as the note. Enforce this in Django validation and, where practical, with database constraints in the migrations.
- The University filter joins through department. The cross-university Department filter uses `disciplines`; each `academic_departments` row represents one institution's actual department. Subject options can be derived from subjects represented in the selected department's published notes or courses.
- Preserve inactive directory records for existing references. Do not allow inactive entries on newly created or reclassified notes.

## Publishing and files

- `notes.publisher_id` is the account ID, never the display name. Only `published` notes appear in Explore and public profile lists.
- A draft or pending-review note may have no PDF, but publishing requires a valid `note_pdf_assets` row and a `published_at` timestamp. `published_at` is null until first publication; archiving does not erase it. `moderation_hidden_at` and `deleted_at` independently remove a note from public results.
- `notes.kind` captures the optional type used by the Share note form (lecture notes, exam prep, problem set, study guide, or other).
- This phase models one current PDF per note. A future revision history can add a separate versions table without changing the note ID. Store the PDF in managed file storage; `storage_key` is internal and must not be returned as a raw public path.
- External resource links live in `note_resources`, with zero to five rows per note. Enforce `position BETWEEN 1 AND 5` in a database `CHECK` constraint and keep `(note_id, position)` unique; together these guarantee a maximum of five. Each row has a required label and URL. Validate allowed URL schemes and render links safely. The note PDF is separate in `note_pdf_assets` and does not use one of these five slots.
- Search should cover title, descriptions, course code/name, subject name, department code/name, and university code/name. Start with measured Django queries; add MySQL FULLTEXT or other suitable indexes after query behavior and scale are defined. The DBML indexes cover basic filtering and ownership.

## Interactions and profile derivation

- `note_likes` and `saved_notes` use one row per user and note. Like counts come from `note_likes`; saved notes are private to the owner.
- Note comments belong to a note and author. A reply's `parent_comment_id` must refer to a comment on the same note and must not form a cycle. `deleted_at` allows the UI to keep a reply thread's shape while hiding removed content.
- The profile's published-note count/list is derived from `notes` filtered by `publisher_id` and `status`. Its saved-note count comes from `saved_notes`. The profile Activity tab can later combine timestamped notes with discussion topics and replies.
- The note reader's report action creates a `reports` row under a shared `moderation_cases` item. Multiple students can report the same content without duplicating the review-queue item.

## Open decisions

- Whether notes require review before publication.
- Whether publishers may replace PDFs and whether prior versions remain accessible.
- Whether course selection is optional for every institution and how department codes are standardized across universities.
- Whether note comments support nested replies beyond one level and how deletions are retained.
