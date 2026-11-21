## Quy tắc cần nhớ khi yêu cầu commit 
lúc đưa lên git comment theo chuẩn Conventional Commits
• feat. Dùng khi thêm một tính năng mới cho người dùng.
• fix. Dùng khi sửa một lỗi (bug) trong hệ thống.
• docs. Dùng khi chỉ thay đổi hoặc bổ sung tài liệu hướng dẫn (như file README).
• style. Dùng khi chỉnh sửa định dạng code (dấu cách, dấu chấm phẩy, thụt lề) mà không làm thay đổi logic chạy.
• refactor. Dùng khi cấu trúc lại code cho gọn gàng hơn nhưng không thêm tính năng hay sửa lỗi.
• test. Dùng khi thêm mới hoặc chỉnh sửa các bài kiểm thử tự động.
• chore. Dùng cho các việc lặt vặt như cập nhật thư viện, cấu hình công cụ build mà không đụng tới code chính.

Read the complete CloudStock BE2 Implementation Runbook.

## Execute STEP 1 only.

I want implementation work, not another architecture-planning cycle.

1. Inspect the current branch and run `git status --short`.
2. Preserve every pre-existing modification and untracked file.
3. Inspect the current backend tree, SAM template, handlers, common utilities, scripts, and tests.
4. Run the existing backend unit tests using the environment already installed. Do not install packages.
5. Identify the smallest useful BE2 task that can be implemented in new isolated files without modifying existing teammate/shared files.
6. Start implementing that isolated task in this STEP. Prefer a migration dry-run/verification module or another clearly isolated backend utility that is genuinely needed by the agreed architecture.
7. Do not run any migration against real data. The migration tool must default to dry-run and require an explicit, separate execution flag for any write operation. Do not add production execution capability that can be triggered accidentally.
8. Add tests in a new isolated test file if possible. Do not edit the shared existing test file without approval.
9. If no useful implementation can be done without changing a shared file, do not invent work. Show the exact minimal file change needed and stop only for that specific approval.
10. Do not modify frontend, README files, architecture DOCX, SAM infrastructure, AWS resources, database contents, or Git state.

At the end:
- List files created/modified.
- Explain the implemented behavior.
- Show exact test commands and actual results.
- Show `git status --short` and `git diff --`.
- Confirm all pre-existing changes were preserved.
- Do not start STEP 2.

## Execute STEP 2 from the CloudStock BE2 Implementation Runbook only.

Implement reusable compatibility helpers in new isolated backend module(s), plus new isolated tests.

Required behavior:
1. Normalize product legacy `quantity` and canonical `stockQuantity`.
2. Normalize transaction legacy `amount` and canonical `quantity`.
3. Normalize legacy `timestamp` and canonical `createdAt`.
4. Normalize legacy transaction `type=IN/OUT` and temporary `canonicalType=IMPORT/EXPORT`.
5. Detect conflicting values. Never silently overwrite a conflict.
6. Preserve `requestHash` and existing idempotency behavior; do not reimplement or alter the current transaction handler in this STEP.
7. Add tests for legacy-only, canonical-only, matching dual fields, conflicting dual fields, invalid types, and missing required fields.
8. Do not modify existing handlers, shared utilities, SAM template, frontend, README, architecture DOCX, or existing shared test files.
9. Run only relevant tests and report actual results.

Stop after STEP 2. Do not integrate the helpers into existing handlers yet.

## Execute STEP 3 from the CloudStock BE2 Implementation Runbook only.

Integrate the approved compatibility helpers into the existing Products handler.

Before editing:
1. Show current `git status --short`.
2. Inspect the exact current diff and preserve unrelated changes.
3. Confirm that I have approved editing `backend/src/products/__init__.py`. If this approval is not present in the conversation, STOP and request approval for this exact file only.

Implementation:
- Read canonical `stockQuantity`, fallback to legacy `quantity`.
- Dual-write `stockQuantity` and legacy `quantity` during compatibility period.
- Detect and report conflicts; do not silently choose a conflicting value.
- Compute `status` from stock quantity.
- Low-stock rule is `stockQuantity <= minThreshold`.
- Keep physical product PK unchanged.
- Preserve current CRUD behavior, validation, response envelope, and pagination.
- Keep image compatibility behavior unchanged in this STEP; do not implement S3 upload here.
- Do not modify transaction, supplier, frontend, SAM, README, or architecture files.

Add/extend tests only in approved test files. If the shared test file is not approved, create isolated tests where practical.

Run relevant tests, show exact diffs, and stop.

## Execute STEP 4 from the CloudStock BE2 Implementation Runbook only.

Before editing:
1. Show `git status --short`.
2. Inspect the exact transaction handler and its current tests.
3. Confirm explicit approval to edit `backend/src/transactions/__init__.py`. If not approved, STOP and request approval for this exact file.

Implementation:
- Preserve physical PK `transactionId`.
- Preserve GSI `ByTimestamp`, `gsi1pk`, and `gsi1sk`.
- Use `createdAt` as canonical timestamp.
- Continue generating `gsi1sk` as `createdAt#transactionId`.
- During compatibility, dual-write `timestamp` and `createdAt`.
- Preserve legacy `type=IN/OUT`; write temporary `canonicalType=IMPORT/EXPORT`.
- Dual-write `amount` and `quantity` with the same numeric value.
- API responses should expose canonical fields while preserving any legacy fields required by existing frontend consumers.
- Preserve `Idempotency-Key`, `requestHash`, and replay/mismatch behavior.
- Preserve atomic stock update and transaction creation.
- Never allow negative stock.
- `performedBy` must come from Cognito claims.
- Filter out reservation records from transaction listing and detail responses.
- Do not implement upload reservations in this STEP.
- Do not change S3, routes, frontend, template, or README.

Test IMPORT, EXPORT, insufficient stock, idempotent replay, idempotency mismatch, legacy/canonical serialization, and GSI sort-key construction.

Show exact diffs and test results. Stop after STEP 4.

## Execute STEP 5 from the CloudStock BE2 Implementation Runbook only.

Implement product-image upload support using S3 presigned PUT and one-time upload reservations.

Before editing, list exact files and classify new isolated files versus existing shared/infrastructure files. Do not edit a shared file or `backend/template.yaml` without explicit approval.

Required design:
1. Generate S3 keys on the backend under `products/`.
2. Create a reservation bound to Cognito subject, generated key, allowed content type/size, expiry, and PENDING state.
3. Return a short-lived presigned PUT URL.
4. Verify uploaded object metadata before attaching it to a product.
5. Consume the reservation exactly once.
6. In a DynamoDB transaction, use ONE conditional Update action for the reservation item: require PENDING, unexpired, and owned by the authenticated subject; set CONSUMED and record the product ID.
7. Do not target the same reservation item with separate ConditionCheck and Update actions in one TransactWriteItems.
8. Persist the full public HTTPS product image URL, not a presigned URL.
9. Keep product legacy imageKey compatibility during the rollback window.
10. Do not enable bucket-wide public access. Follow the approved public `products/` prefix policy only.
11. Do not upload to or modify the real AWS bucket.
12. Do not enable DynamoDB TTL or modify infrastructure unless separately approved.

Add unit tests with mocked S3/DynamoDB calls. Do not edit frontend. Stop after STEP 5.

# STEP 5B – Fix Two Audit Findings

STEP 5A identified exactly two issues. Fix only these issues before proceeding to STEP 6.

## 1. Mandatory pre-check

Inspect:
- `backend/template.yaml`
- `backend/src/product_images/__init__.py`
- Existing product image tests.
- Current Git status and diffs.

Preserve all existing changes.

## 2. Fix IAM permissions

In `backend/template.yaml`:

- Restrict `dynamodb:PutItem` to the Transactions table only.
- Keep `dynamodb:TransactWriteItems` scoped to the exact tables required by the image upload transaction.
- Preserve all other required S3 and DynamoDB permissions.
- Do not grant wildcard DynamoDB table access.
- Do not weaken existing permissions or change unrelated resources.

Verify that the image upload flow still has the permissions required for its actual DynamoDB operations.

## 3. Fix reservation key format

In `backend/src/product_images/__init__.py`:

Replace the current reservation key format:

`UPLOAD#IMAGE#<uuid>`

with the agreed format:

`UPLOAD#<random>`

Requirements:

- Keep `recordType=UPLOAD_RESERVATION`.
- Keep reservation ownership, product association, expiry, state, and conditional-consumption behavior unchanged.
- Keep reservation items excluded from the ByTimestamp GSI.
- Ensure creation, lookup, completion, and consumption all use the same key format.
- Do not change the Transactions physical partition key or GSI.
- Do not change the upload API contract unless technically unavoidable; if unavoidable, stop and explain first.

## 4. Tests

Add or update focused tests verifying:

1. New reservation keys use exactly `UPLOAD#<random>`.
2. Reservation completion finds the same reservation.
3. A reservation cannot be consumed twice.
4. Reservation ownership and expiry checks remain enforced.
5. IAM `PutItem` is scoped only to Transactions.
6. `TransactWriteItems` includes only the required table resources.
7. Existing product image upload tests still pass.

Run the full backend suite:

`python -m unittest discover -s test -v`

Run `git diff --check`.

Do not install SAM CLI or access AWS.

## 5. Strict file scope

You are authorized to modify only:

- `backend/template.yaml`
- `backend/src/product_images/__init__.py`
- `backend/test/test_product_images.py`

Do not modify any other file.

Do not deploy, stage, commit, or push.

## 6. Completion report

Report:
- Exact changes made.
- IAM permission scope before and after.
- Reservation key format before and after.
- Test results.
- `git diff --check` result.
- Relevant diffs.
- Final `git status --short`.

Stop after STEP 5B. Do not start STEP 6.


## Execute STEP 6 from the CloudStock BE2 Implementation Runbook only.

Implement private invoice upload and retrieval.

Before editing, request approval for each existing shared handler/template file required. Do not edit unapproved files.

Required behavior:
1. Generate invoice object keys only under private `invoices/`.
2. Bind reservation to authenticated Cognito subject, generated key, content type, size, expiry, and PENDING state.
3. Issue short-lived presigned PUT URL.
4. Verify object metadata before attaching.
5. Consume reservation with one conditional Update action, not separate actions against the same reservation item.
6. Atomically consume reservation and create the transaction; include stock update when required by the transaction flow.
7. Store stable private S3 key in transaction data. Never store presigned URL.
8. Implement retrieval by transaction ID, not arbitrary client-supplied S3 key.
9. Check Admin/Staff authorization and confirm the transaction exists before returning a short-lived presigned GET URL.
10. Never make `invoices/` public.
11. Keep legacy `invoiceKey` compatibility while the rollback window remains.
12. Do not access or modify real S3 objects.

Approved for STEP 6 only, with the following strict constraints.

You may modify only:
- `backend/src/transactions/__init__.py`
- `backend/template.yaml`
- `backend/scripts/local_api.py`

Implementation requirements:

1. Invoice upload
- Use the existing S3 bucket.
- Store invoice objects only under the private `invoices/` prefix.
- Do not add public read permissions, ACLs, or bucket-wide public access.
- Generate S3 object keys on the backend; never accept arbitrary client-provided S3 keys or URLs.
- Bind each invoice reservation to the authenticated Cognito subject, expiry, expected content type/size, and reservation state.
- Validate the uploaded object before allowing it to be attached to a transaction.

2. Atomic transaction integration
- Accept `invoiceReservationId` in transaction creation.
- Validate and consume the reservation using one conditional Update action in the same `TransactWriteItems` operation as the stock update and transaction creation.
- Do not use separate `ConditionCheck` and `Update` actions against the same reservation item.
- Preserve existing stock validation, no-negative-stock behavior, idempotency/requestHash behavior, and transaction PK/GSI structure.
- Ensure reservation consumption cannot be replayed or used by another user or transaction.

3. Invoice retrieval
- Retrieve invoices only after authenticating and authorizing the requester and looking up the associated transaction.
- Generate a short-lived presigned GET URL only after those checks.
- Store the stable private S3 object key in the transaction's invoice compatibility fields, never a presigned URL.
- Do not expose invoice keys or retrieval access to unauthorized users.

4. Compatibility and scope
- Preserve all existing product-image upload behavior from STEP 5.
- Do not change frontend files, shared utilities, other handlers, tests outside the approved scope, or unrelated transaction behavior.
- Do not remove legacy fields or change the existing transaction schema/GSI design.
- If implementation requires any additional file, stop and request approval before modifying it.

5. Verification
- Add tests for reservation ownership, expiry, invalid/missing objects, one-time consumption, unauthorized retrieval, idempotent retries, and atomic transaction behavior.
- Test that invoice objects remain private and IAM permissions are limited to the required bucket prefix and actions.
- Run the invoice-specific tests, full backend test suite, and `git diff --check`.
- Report exact changed files and test results.

Do not access AWS, deploy, upload real objects, stage, commit, or push. Do not start another step after STEP 6.

Add mocked tests for authorization, ownership, expiry, missing object, duplicate attachment, and presigned GET generation. Stop after STEP 6.

## Execute STEP 7 from the CloudStock BE2 Implementation Runbook only.

Implement the backend dashboard endpoint using existing DynamoDB data.

Target route: `GET /dashboard`.

Before editing, identify the exact handler and SAM route files. Request approval for shared/infrastructure files before editing them.

Requirements:
- Return dashboard values derived from Products and Transactions.
- Use canonical transaction values through compatibility helpers.
- Respect `IN/OUT` and `IMPORT/EXPORT` compatibility.
- Calculate total products, total stock quantity, low-stock count using `stockQuantity <= minThreshold`, out-of-stock count, and import/export summaries where supported by the current data.
- Do not invent financial metrics that cannot be derived from stored fields.
- Restrict access to Admin/Staff.
- Keep response shape consistent with existing API conventions.
- Do not edit frontend.
- Add unit tests with mocked DynamoDB responses.
- Do not deploy.

Stop after STEP 7.

## Execute STEP 8 from the CloudStock BE2 Implementation Runbook only.

Implement Admin-only Cognito user management.

Target routes:
- GET /users
- POST /users
- PUT /users/{username}/role
- DELETE /users/{username}

Before editing, request approval for SAM template and shared authorization files.

Requirements:
- Only Admin can list/create/change role/disable users.
- Support only existing Cognito groups `Admin` and `Staff`.
- Use Cognito Admin APIs.
- Prefer disabling a user over physical deletion to preserve audit identity.
- Prevent self-disable.
- Prevent disabling the last Admin.
- Validate role input and username.
- Never return passwords, tokens, secrets, or sensitive Cognito attributes.
- Do not create a new User Pool or App Client.
- Do not create real Cognito users or call AWS.
- Add mocked unit tests for authorization, validation, role changes, self-disable, and last-admin protection.

Stop after STEP 8.

## Execute STEP 9 from the CloudStock BE2 Implementation Runbook only.

Implement Admin-only CloudWatch log retrieval.

Target route: `GET /transactions/logs`.

Before editing, request approval for SAM template and shared files.

Requirements:
- Admin only.
- Use CloudWatch Logs APIs with bounded time range, page size, and pagination.
- Validate all query parameters.
- Do not allow arbitrary log group access from the client.
- Use only the approved CloudStock Lambda log groups.
- Add least-privilege IAM permissions for the required log actions, but do not edit template until approved.
- Do not return secrets or credentials from logs; redact sensitive values where applicable.
- Do not call real CloudWatch or deploy.
- Add mocked unit tests.

Stop after STEP 9.

## Execute STEP 10 from the CloudStock BE2 Implementation Runbook only.

Review the local API adapter and local DynamoDB initializer.

Before editing, request approval for each shared local infrastructure file.

Requirements:
- Add only routes whose backend handlers have already been implemented and tested.
- Keep local adapter bound to `127.0.0.1`.
- Preserve the existing localhost origin restriction.
- Preserve local Admin/Staff authentication behavior.
- Do not weaken Cognito authorization in deployed API.
- Keep local and deployed response contracts aligned.
- Do not add mock success responses for endpoints that are not implemented.
- Do not modify frontend in this STEP.
- Run adapter tests and route tests.
- Do not alter or delete the user's local DynamoDB data unless explicitly approved.

Stop after STEP 10.

## Execute STEP 11 from the CloudStock BE2 Implementation Runbook only.

Perform a final backend integration verification.

1. Run all backend unit tests.
2. Run SAM template validation only if SAM CLI is already installed.
3. Check Python syntax/imports.
4. Check every implemented route against the API contract.
5. Check Cognito group authorization.
6. Check transaction atomicity and idempotency.
7. Check legacy/canonical compatibility.
8. Check that reservation items cannot leak into transaction list/detail.
9. Check product images are public only under the approved prefix.
10. Check invoices remain private and require presigned retrieval.
11. Check no secret or credential was added to source, docs, or logs.
12. Check no frontend files were modified.
13. Check `git status --short` and full diff.

Do not deploy, migrate real data, change AWS resources, commit, push, or modify protected README/DOCX files.

Return:
- Implemented features.
- Routes implemented.
- Test commands and actual results.
- Known limitations.
- Files changed.
- Any remaining approvals needed.
- Confirmation that protected files and unrelated changes remain untouched.

Stop after STEP 11.