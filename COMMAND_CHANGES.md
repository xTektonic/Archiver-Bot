# Command Change Log

The rewrite keeps the current command names unless listed below. Any future rename or description change should be recorded here so staff workflows can be restored if needed.

| Old command | Old description | New command | New description | Reason | Safe to revert |
| --- | --- | --- | --- | --- | --- |
| `/close_resolved` | Closes all solved, rejected and archived posts | `/close_resolved` | Close solved/rejected/archived posts | Shorter wording; behavior preserved with `dry_run` option added. | Yes |
| `/open_archived` | Opens all posts in the archive | `/open_archived` | Open archived archive posts | Clarifies target posts; behavior preserved with `dry_run` option added. | Yes |
| `/tag_selector` | Edit the tags of a forum post | `/tag_selector` | Set forum post tags | Shorter wording; behavior preserved. | Yes |
| `/tracker_list` | Rechecks and resends the submission tracker list | `/tracker_list` | Rebuild the submission tracker summary | Matches new state-backed tracker behavior. | Yes |
| `/parse_archive` | Parse the posts in the archive and check for errors | `/parse_archive` | Parse all configured archive forums | Clarifies configured category scope. | Yes |
