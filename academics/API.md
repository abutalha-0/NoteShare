# Academic directory API

Base path: `/api/v1/academics/`. These records are shared by profile affiliations and note filters. A **discipline** is a field across universities; a **department** is a university-specific unit linked to one discipline. A **course** belongs to a department and a subject.

| Collection | Fields for `POST` | List filters |
| --- | --- | --- |
| `universities/` | `code`, `name`, optional `is_active` | `q` |
| `disciplines/` | `code`, `name`, optional `is_active` | `q` |
| `departments/` | `university_id`, `discipline_id`, `code`, `name`, optional `is_active` | `q`, `university`, `discipline` |
| `subjects/` | `slug`, `name`, optional `is_active` | `q` |
| `courses/` | `department_id`, `subject_id`, `code`, `name`, optional `is_active` | `q`, `department`, `subject`, `university` |

`GET /<collection>/` returns `{ "count": n, "limit": 50, "offset": 0, "results": [...] }`. Use `limit` (1–100) and `offset` (0 or greater) for pagination. `q` searches name and code, or name and slug for subjects. Filter IDs must be UUIDs. `GET /<collection>/<id>/` returns a single record. Department responses include their university and discipline; course responses include their department, subject, and university.

Unauthenticated reads show active records only. Departments under inactive universities or disciplines, and courses under any inactive parent, are hidden. Administrators may pass `include_inactive=true` with a Bearer access token to see all records.

Administrators can use `POST /<collection>/` to create and `PATCH /<collection>/<id>/` to update records. Both require `Authorization: Bearer <access_token>` for an active account with the `admin` role. Codes are trimmed and uppercased; subject slugs are trimmed and lowercased. An active department must reference an active university and discipline. An active course must reference an active department and subject. Changing `is_active` to `false` hides the record from public lookup; records are retained so existing references remain valid.

Responses use JSON with `Cache-Control: no-store`. Validation errors return `400`, missing records `404`, duplicate or conflicting records `409`, and insufficient authentication `401` or `403`. The API does not delete academic records.
