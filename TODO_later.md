# TODO Later

## Bug: Partial upload failure loses items permanently
- In `octopus.py` `_do_upload()` lines 190-196, after `store_contents` returns, ALL tasks are marked with `items_uploaded = len(task_contents)` and contents are cleared from metadata, even if some individual items failed to upload.
- Failed items are never retried because the task is marked as uploaded.
- **Suggested fix:** Only mark `items_uploaded` based on the actual success count from `store_contents` results. Only clear contents for successfully uploaded items, or keep failed items in metadata for the next `trigger_upload` cycle.
