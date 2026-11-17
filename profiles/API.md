# Profiles API

Base path: `/api/v1/profiles/`. Profile responses use JSON and `Cache-Control: no-store`. The accounts app creates an empty profile for each new user; a migration fills in profiles for accounts that existed before this app was added.

| Endpoint | Access | Purpose |
| --- | --- | --- |
| `GET me/` | Active Bearer token | Read all of your profile fields, privacy settings, and account email |
| `PATCH me/` | Active Bearer token | Update your profile and/or replace ordered interests |
| `GET <user_id>/` | Public | Read a visible user's public profile |
| `POST me/avatar/` | Active Bearer token | Upload an image in multipart field `avatar` |
| `GET me/avatar/` | Active Bearer token | Read your avatar, including when it is private |
| `DELETE me/avatar/` | Active Bearer token | Remove your avatar |
| `GET <user_id>/avatar/` | Public | Read an avatar only when its owner allows it |

`PATCH me/` accepts any subset of `display_name`, `bio`, `university_id`, `department_id`, `interests`, `show_avatar`, `show_bio`, `show_university`, `show_department`, and `show_interests`. Use `null` to clear optional text or academic affiliation and `[]` to clear interests. Interests are an ordered array of up to 10 distinct labels, each up to 80 characters. The selected department must be active and belong to the selected active university. Changes to profile fields and interests are atomic.

Public responses include user ID, display name, join date, and only the bio, academic affiliation, interests, and avatar URL permitted by the privacy settings. Hiding a university also hides its department, even if `show_department` is true. Email, privacy controls, moderation state, and the internal `avatar_key` are never public. Pending, suspended, and moderator-hidden profiles return `404` on public endpoints. Owners can still see their own moderation state while their account remains active.

Avatars must be still JPEG, PNG, or WebP images, no larger than 2 MB or 3000 × 3000 pixels. Uploads are resized to fit within 512 × 512 pixels, encoded as WebP, and served through access-checked endpoints. The API does not expose storage keys or serve the media directory directly. Configure durable private file storage before production deployment.

Public note contributions can be read through `GET /api/v1/notes/?publisher=<user_id>`. An owner can use `GET /api/v1/notes/me/` and `GET /api/v1/notes/me/saved/`. A combined activity feed and discussion counts will be added after the discussions app exists; this API does not return placeholder counts.
