# Fieldnotes database review

**Verdict:** The proposed 24-table schema is suitable for the current UI concept and the agreed maximum of five external resource links per note. It is a design specification, not evidence that Django models or migrations have been implemented. Define and reconcile the intended `AUTH_USER_MODEL` before the first migration.

## UI coverage checked

| UI flow | Source tables | Assessment |
| --- | --- | --- |
| Registration, sign-in, account verification, password reset, JWT refresh and logout | `users`, `password_credentials`, `user_roles`, `auth_sessions`, `auth_action_tokens` | Represented. Match these logical tables to the existing auth implementation; do not create a duplicate user model. |
| Own and public profiles, editing, privacy, interests, contributions and activity | `profiles`, `profile_interests`, `universities`, `disciplines`, `academic_departments`, `notes`, `discussion_topics`, `discussion_replies` | Represented. Contribution counts and activity are queries over source records, with different owner/public visibility rules. |
| Explore search, university/department/subject filters, note cards and likes | `notes`, `subjects`, `courses`, `academic_departments`, `disciplines`, `universities`, `note_likes`, `profiles` | Represented. Search indexes and query behavior belong in the Django/MySQL implementation. |
| Share a note, related resources, reader, PDF access, save and note discussion | `notes`, `note_pdf_assets`, `note_resources`, `saved_notes`, `note_comments` | Represented. One current PDF and zero to five ordered external links are modeled separately. |
| Independent Discussions list, detail and replies to a topic or another reply | `discussion_topics`, `discussion_replies`, `profiles` | Represented. Parent reply IDs preserve conversation structure; group colors are UI styling. |
| Notifications and unread count | `notifications` plus its referenced content and actor | Represented. Event creation and recipient selection require explicit backend rules. |
| Reports and moderator review queue | `moderation_cases`, `reports`, `moderation_actions`, `user_roles` | Represented. Reviewer authorization and target visibility changes require service-level transactions. |

The detailed ownership and page mapping remains in [SCHEMA_PAGE_MAP.md](./SCHEMA_PAGE_MAP.md).

## Integrity rules checked

- Every table has a primary key, every declared foreign key points to an existing table and column, and each of the 24 tables appears in exactly one diagram group.
- `note_resources` uses a position check of 1–5 plus a unique `(note_id, position)` index. Together, these limit each note to five links, including under concurrent requests.
- `profile_interests` similarly uses positions 1–10 and a per-user unique position index. Its normalized label is unique per profile.
- `moderation_cases` and `notifications` each have a check requiring exactly one content target.
- Likes and saved notes each have a composite primary key, preventing duplicates for the same user and note.
- Notes, topics, comments, and replies point to stable author IDs. Changing a display name cannot transfer ownership.

## Implementation conditions before calling the database production-ready

1. **Define the auth model before migrating.** Confirm ID type, email normalization, JWT session/revocation behavior, and roles. The combined DBML is a logical model; it does not create a Django user model by itself.
2. **Implement cross-table rules.** A profile department must belong to its university; a note's optional course must agree with its department and subject; a reply parent must belong to the same note or topic; public notes must have a valid PDF. These are not enforced by the current foreign keys alone.
3. **Implement the remaining database constraints.** Preserve all DBML checks and unique indexes in migrations. MySQL does not support conditional unique indexes; use a generated active-target key with a unique index for one active moderation case per content target. Enforce status/timestamp consistency and use transactions for reporting, moderation, and multi-link updates.
4. **Define visibility and permissions.** Public queries must exclude unpublished, deleted, and moderator-hidden content. Own-profile, saved-note, and notification queries must be scoped to the signed-in user. Moderator tools require server-side role checks.
5. **Define event and notification rules.** The schema can display and target a “new note” notification, but the product has not chosen whether recipients are selected by affiliation, explicit subscriptions, or another rule. Explicit follow controls would require subscription tables before being implemented.
6. **Validate files and links.** PDF size, bytes, page count, storage access and replacement; profile images; and safe external URL schemes are backend responsibilities. Storage keys must not be public API fields.
7. **Test migrations against real data.** Run clean-database migration tests and test the API flows above. Static DBML review alone cannot confirm the database or API behavior.

**Scope note:** The old prototype contains some local-only sample fields such as read counts and “most read” sorting. These are not part of the current Explore Notes design brief. If those controls return to the product, add a deliberate view-count design before implementing them. The sample “new in course” notifications similarly need a defined recipient rule, not necessarily a new table until following is chosen.
