# Which tables power each Fieldnotes page

The groups in [fieldnotes.dbml](./fieldnotes.dbml) show which feature owns each table. A page can read tables from several groups. For example, the note reader gets the note from **Notes**, its publisher from **Profiles**, and its subject from the **Academic directory**.

## Table categories

| Category | Tables | Responsibility |
| --- | --- | --- |
| Authentication | `users`, `password_credentials`, `user_roles`, `auth_sessions`, `auth_action_tokens` | Accounts, sign-in, roles, sessions, password and email actions. The Django `AUTH_USER_MODEL` remains the real account model. |
| Academic directory | `universities`, `disciplines`, `academic_departments`, `subjects`, `courses` | Names and relationships used by profile fields and note filters. A discipline is a cross-university field; a department belongs to one university. |
| Profiles | `profiles`, `profile_interests` | Public identity, bio, avatar reference, academic affiliation, and interests. |
| Notes | `notes`, `note_pdf_assets`, `note_resources`, `note_likes`, `saved_notes`, `note_comments` | Shared notes, PDF files, up to five resource links, likes, bookmarks, and discussion attached to a note. |
| Discussions | `discussion_topics`, `discussion_replies` | Independent discussion threads and nested replies. |
| Notifications | `notifications` | Inbox items and read state. |
| Moderation | `moderation_cases`, `reports`, `moderation_actions` | Reports, review queue, and recorded moderator decisions. |

## Page-to-table map

| Page or UI area | Main tables | Other tables read | What they provide |
| --- | --- | --- | --- |
| Sign up, sign in, password reset | `users`, `password_credentials`, `auth_sessions`, `auth_action_tokens` | `user_roles` | Account identity, credentials, login state, verification/reset actions, and permissions. |
| Own profile and Edit profile | `profiles`, `profile_interests` | `users`, `universities`, `academic_departments`, `disciplines`, `notes`, `discussion_topics`, `discussion_replies`, `saved_notes` | Editable identity and affiliation; own notes, discussions, saved notes, and derived activity. |
| Other user's profile | `profiles`, `profile_interests` | `users`, `universities`, `academic_departments`, `disciplines`, `notes`, `discussion_topics`, `discussion_replies` | Public identity and public contributions. Private account fields and drafts stay hidden. |
| Explore Notes | `notes` | `subjects`, `courses`, `academic_departments`, `disciplines`, `universities`, `profiles`, `users`, `note_likes` | Searchable note cards, academic filters, publisher names, and like counts. |
| Share Note | `notes`, `note_pdf_assets`, `note_resources` | `subjects`, `courses`, `academic_departments`, `users` | Note metadata, academic classification, publisher ownership, uploaded PDF, and up to five external links. |
| Note detail and PDF reader | `notes`, `note_pdf_assets`, `note_resources`, `note_likes`, `saved_notes`, `note_comments` | `users`, `profiles`, `subjects`, `academic_departments`, `universities` | Note information, publisher link, readable/downloadable PDF, ordered resources, like/save state, and note discussion. |
| Saved Notes | `saved_notes` | `notes`, `note_pdf_assets`, `profiles`, `users` | The current user's saved list and each note's visible summary. |
| Discussions list and search | `discussion_topics` | `discussion_replies`, `users`, `profiles` | Topic titles/descriptions, authors, and derived reply counts. |
| Discussion detail | `discussion_topics`, `discussion_replies` | `users`, `profiles` | Full thread, reply ancestry, and who is replying to whom. |
| Notifications | `notifications` | `users`, `profiles`, `notes`, `note_comments`, `discussion_topics`, `discussion_replies`, `moderation_cases` | Event text, actor, linked destination, unread state, and access checks before opening a target. |
| Report control and moderator review queue | `reports`, `moderation_cases`, `moderation_actions` | `users`, `profiles`, `notes`, `note_comments`, `discussion_topics`, `discussion_replies` | Submitted reports, reported content, queue status, and decisions. |

**Derived display values:** Profile activity and contribution counts come from `notes`, `discussion_topics`, and `discussion_replies`. Note likes come from `note_likes`; discussion reply counts come from `discussion_replies`. These do not need separate tables in the current design.

**UI-only state:** Search text, expanded filters, active tabs, reply composer state, and the locally stored dark-mode preference do not require database tables. If these become cross-device preferences or saved searches, extend the schema then.
