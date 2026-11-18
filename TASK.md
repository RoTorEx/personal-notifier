# Missing-notification incident

- Fix the producer/consumer photo_urls contract through real FeedClient validation.
- Add a queue-summary-only event read to avoid unrelated listing-update backlog;
  prevent collection-scope metadata from generating artificial source updates.
- Audit every Housing/Market category against persisted source decisions and
  representative live offers; preserve the owner/Ira scopes and review state.
- Publish/deploy verified patches. Recover only genuinely missed post-reset
  discoveries in one catch-up event per topic, through the normal sender and
  real recipient receipts, without replaying historical individual summaries.
- Record evidence, remaining platform limitations, recovery points and cleanup.
