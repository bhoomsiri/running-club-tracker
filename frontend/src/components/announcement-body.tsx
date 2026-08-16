/**
 * The text of a notice.
 *
 * Rendered as plain text with its line breaks kept, never as HTML. The body is free text
 * typed into a form, and the landing page shows it to the public — putting it through
 * `dangerouslySetInnerHTML` would turn the admin form into a way to inject script into
 * the club's own front page. `whitespace-pre-line` gives paragraphs and lists their
 * shape back without any of that.
 */
export function AnnouncementBody({
  body,
  className = "",
}: {
  body: string;
  className?: string;
}) {
  return <p className={`whitespace-pre-line text-muted ${className}`}>{body}</p>;
}
