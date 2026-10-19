import type { Metadata } from "next";
import Link from "next/link";
import { Contact, UPDATED } from "../../components/ui";

export const metadata: Metadata = { title: "Terms of service" };

export default function Terms() {
  return (
    <div className="wrap stack legal" style={{ gap: 32 }}>
      <h1 className="display d-l">Terms of service</h1>
      <p className="mono">Last updated {UPDATED}</p>
      <p className="lead">By using TasteRoute you agree to these terms. If you don&apos;t agree, please don&apos;t use it.</p>

      <section className="stack-s">
        <h2 className="h2">The service</h2>
        <p>
          TasteRoute ranks venues by how well their guests&apos; taste matches your brand (using Qloo), finds the business emails venues publish, and drafts
          a first email for you to review. It is an early, free service, provided as is, and it may change or stop at any time.
        </p>
      </section>

      <section className="stack-s">
        <h2 className="h2">What the results mean</h2>
        <ul>
          <li>Taste fit is a starting list, not a sales forecast. It shows whose guests may like what you make; it doesn't predict orders.</li>
          <li>Drafts are written by an AI from the facts shown. Read and edit every draft before you send it; you are responsible for what it says.</li>
          <li>Contacts are public business addresses and may be out of date.</li>
        </ul>
      </section>

      <section className="stack-s">
        <h2 className="h2">Sending email</h2>
        <ul>
          <li>You are the sender. Emails go from your own Gmail, one per click, or you copy them into your own email app.</li>
          <li>Follow the email and privacy laws that apply to you and the people you write to (for example CAN-SPAM, GDPR or PECR).</li>
          <li>Send relevant, honest business pitches only: no bulk or unsolicited mass mail, no false claims, no misleading subjects.</li>
          <li>Keep the opt-out line, and honour every opt-out: add the address to your do-not-contact list.</li>
          <li>Sending through Gmail is also subject to Google&apos;s terms and sending limits.</li>
        </ul>
      </section>

      <section className="stack-s">
        <h2 className="h2">Fair use</h2>
        <p>
          Don&apos;t misuse TasteRoute: no scraping or reselling its data, no attempts to break its limits or get into other people&apos;s workspaces, and no use
          that harms the venues listed. Venue and map data come from Qloo and from OpenStreetMap contributors (Open Database License). We may limit or end
          access for anyone who misuses the service.
        </p>
      </section>

      <section className="stack-s">
        <h2 className="h2">Your content and account</h2>
        <p>
          Your brand details and drafts stay yours. You let us store and process them to run the service, as the <Link href="/privacy">privacy policy</Link>{" "}
          describes. Logging in is optional; you can log out at any time and ask us to delete your data.
        </p>
      </section>

      <section className="stack-s">
        <h2 className="h2">No warranty</h2>
        <p>
          TasteRoute is provided &ldquo;as is&rdquo;, without warranties of any kind. To the extent the law allows, we aren&apos;t liable for lost sales, missed
          emails, or other indirect losses from using it.
        </p>
      </section>

      <section className="stack-s">
        <h2 className="h2">Changes and contact</h2>
        <p>If these terms change, we update the date above. Questions: <Contact />.</p>
      </section>
    </div>
  );
}
