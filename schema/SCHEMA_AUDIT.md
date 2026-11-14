# Fieldnotes schema audit

**Source of truth for the proposed data model:** [fieldnotes.dbml](./fieldnotes.dbml). It contains 24 tables covering the current product concept. The DBML `users` table is a logical specification for the custom `AUTH_USER_MODEL`; define that model before the first Django migration. MySQL adaptations are recorded in [README.md](./README.md).

For a feature-grouped diagram and a page-by-page explanation of table ownership, see [SCHEMA_PAGE_MAP.md](./SCHEMA_PAGE_MAP.md).

## Coverage of the current UI

| UI surface | Tables that supply it |
| --- | --- |
| Sign-in, account roles, session renewal | `users`, `password_credentials`, `user_roles`, `auth_sessions`, `auth_action_tokens` |
| Own and public profile, edit form | `profiles`, `profile_interests`, `universities`, `academic_departments`, `disciplines` |
| Explore search and filters | `notes`, `subjects`, `courses`, `academic_departments`, `disciplines`, `universities` |
| Note cards, reader, publisher, PDF, resource links | `notes`, `note_pdf_assets`, `note_resources`, `users`, `profiles` |
| Note likes and saved list | `note_likes`, `saved_notes` |
| Discussion inside a note | `note_comments` |
| Independent Discussions list and thread | `discussion_topics`, `discussion_replies` |
| Profile contribution counts and Activity | Derived from `notes`, `discussion_topics`, and `discussion_replies` |
| Notification inbox and unread count | `notifications` |
| Report note and moderator review queue | `moderation_cases`, `reports`, `moderation_actions` |

No table is needed for the discussion group's display color, the compact reply composer, search input state, filter panel state, dark mode stored locally, or the profile tabs. They are presentation state. The prototype's old discussion `votes` values are unused by the current discussion UI, so this schema does not invent a voting feature.

## Database rules to implement in migrations

DBML shows tables and references. The following rules must be implemented in MySQL constraints, indexes, and/or transactional Django services:

1. **Identity and lookup.** Normalize email and directory codes consistently and enforce case-insensitive uniqueness. Use stable user UUIDs for ownership; never join by display name. Moderator privileges come from authorized role assignment, not a client-supplied role.
2. **Academic consistency.** A profile's department must belong to its university. A note's university comes through its department. If a note has a course, the course's department and subject must match the note's department and subject. Use the shared `disciplines` table for cross-university department filtering.
3. **Publication.** A public note must have `status = published`, `moderation_hidden_at IS NULL`, and `deleted_at IS NULL`. Publishing requires a PDF asset and `published_at`. A draft can be incomplete. Decide whether the `pending_review` state is used before enabling publication; its presence does not force review.
4. **Files.** `note_pdf_assets` is one current PDF per note. Validate actual PDF bytes, size, page count, and storage access in the backend. `storage_key` and profile `avatar_key` are internal storage identifiers, not public URLs. File deletion/replacement and database changes require a coordinated cleanup process.
   **External resources.** `note_resources` stores zero to five ordered links per note. Preserve its DBML `CHECK (position BETWEEN 1 AND 5)` and unique `(note_id, position)` index in the Django migration. These two constraints enforce the cap even with concurrent writes. Replace or reorder links atomically so a temporary position collision does not fail midway. Validate URLs and allow safe schemes only. The PDF does not count toward the five links.
5. **Replies.** `note_comments.parent_comment_id` must reference the same `note_id`; `discussion_replies.parent_reply_id` must reference the same `topic_id`. Reject self-parenting and cycles. A null parent means a response to the original note/topic. Soft-deleted or moderator-hidden content is omitted or shown as a minimal placeholder according to the UI policy, while the thread structure remains intact.
6. **Moderation target.** Preserve the DBML check requiring exactly one of the five target foreign keys in `moderation_cases` to be non-null. Keep at most one active case per target with a generated active-target key and unique index for open/reviewing cases; MySQL does not support conditional unique indexes. `reports` permits one reporter per case; a later case can be opened after resolution. Apply a moderation action and any target visibility/account-status change in one transaction. `moderation_actions.affected_user_id` is required when suspending an account so the audit trail names the affected account. Only authorized moderators can create actions.
7. **Notification target.** Preserve the DBML check requiring exactly one notification target. The target type must match `kind`. `recipient_id` owns `read_at`; clients cannot mark another user's notifications read. Do not notify a user of their own action. The UI can group multiple note-like events for display without storing a false like count in the notification row. Opening a notification must re-check access to its target.
8. **Deletion and integrity.** Prefer soft deletion for authored notes, comments, discussion topics, and replies so saved links, moderation history, notifications, and conversation structure do not dangle. Protect referenced academic records and authored content from accidental hard deletion. Define account-erasure and retention policy separately before implementing permanent deletion.
9. **Time and text.** Use timezone-aware timestamps, non-empty trimmed titles/bodies, bounded text lengths, and `updated_at` on edits. Maintain status/timestamp consistency, such as `resolved_at` only for resolved cases and `closed_at` only for closed topics.

MySQL 8 can enforce the same-row exactly-one-target checks in the DBML. It cannot enforce cross-table matching or publication-with-PDF through a plain `CHECK`; use appropriate foreign-key design, triggers, or transactional services. Model the one-active-case rule with a generated key and unique index in a migration.

## Query rules for profile and public pages

- Public profile note count/list: only published, visible, non-deleted notes by `publisher_id`.
- Own profile note list: owner's content, including drafts if the UI provides a private management view; keep public and owner serializers separate.
- Public discussion count/list: visible, non-deleted topics by `author_id`.
- Reply count: visible, non-deleted replies by `author_id` under visible topics.
- Activity: union published note events (`published_at`), started topics (`created_at`), and authored replies (`created_at`), ordered by event time. No separate activity table is necessary for this UI.
- Saved-note count/list: only rows in `saved_notes` for the authenticated user. A saved note later hidden or archived should show a clear unavailable state rather than leak its PDF.
- Note likes and discussion reply counts are derived from relationship rows, not copied into the parent record. Add cached counters only if measured load later warrants them.

## Migration order

1. Define the custom `AUTH_USER_MODEL` before the first migration; do not migrate Django's default user table and replace it later.
2. Academic directory and profile: `universities`, `disciplines`, `academic_departments`, `profiles`, `profile_interests`, `subjects`, `courses`.
3. Notes: `notes`, `note_pdf_assets`, `note_resources`, `note_likes`, `saved_notes`, `note_comments`.
4. Discussions: `discussion_topics`, `discussion_replies`.
5. Moderation: `moderation_cases`, `reports`, `moderation_actions`.
6. Notifications: `notifications`, after source events and permission rules are defined.

## Decisions not settled by a diagram

- Whether anonymous visitors can read notes, discussions, and public profiles.
- Whether every note publishes immediately or enters moderator review.
- PDF replacement/version history and file retention.
- Edit/delete permissions and time limits for notes, topics, and replies.
- Whether note comments allow deep nesting in the UI.
- Whether users can follow notes, subjects, or universities; no follow table is included because the current UI has no follow control.
- Which events should generate notifications and how likes should be grouped.
- Whether profile fields are public by default and how account erasure affects authored content.

These choices affect permissions and workflow. The schema keeps stable IDs and separate status/visibility fields so the choices can be made before implementing the corresponding Django app without changing the main relationships.
