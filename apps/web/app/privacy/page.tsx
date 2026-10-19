import type { Metadata } from "next";
import Link from "next/link";
import { Contact, UPDATED } from "../../components/ui";

export const metadata: Metadata = { title: "Privacy policy" };

export default function Privacy() {
  return (
    <div className="wrap stack legal" style={{ gap: 32 }}>
      <h1 className="display d-l">Privacy policy</h1>
      <p className="mono">Last updated {UPDATED}</p>
      <p className="lead">
        TasteRoute helps food and drink brands find venues whose guests share their taste, and drafts a first email to each.
        This page says what we store, who we share it with, and what you can do about it.
      </p>

      <section className="stack-s">
        <h2 className="h2">What we store</h2>
        <ul>
          <li><strong>Your work.</strong> The brand profile and products you enter, the text we read from the website you give us, your runs (ranked venues and the reasons), contacts found, drafts and your do-not-contact list.</li>
          <li><strong>A workspace token</strong> in your browser&apos;s local storage, so your runs come back when you return. Without logging in, clearing your browser data loses access to them.</li>
          <li><strong>If you log in:</strong> your Supabase user id and email address, so your runs follow you to any device. We never see your password; Google signs you in.</li>
          <li><strong>Your IP address</strong>, only as a salted hash, to limit how many runs one visitor can start.</li>
          <li><strong>A log of each run</strong>: the calls made to Qloo, the AI model and other services, so every number and reason can be traced.</li>
        </ul>
        <p>We use no advertising, no analytics and no tracking cookies.</p>
      </section>

      <section className="stack-s">
        <h2 className="h2">Gmail</h2>
        <p>
          When you log in, we ask Google for one permission: <strong>send email on your behalf</strong> (<code>gmail.send</code>).
          It can&apos;t read your inbox, contacts or any other Google data, and we don&apos;t ask for more.
        </p>
        <ul>
          <li>We send an email only when you click <strong>Send with Gmail</strong> on that draft: one click, one email, to the address shown.</li>
          <li>Google&apos;s access token stays in your browser for about an hour. It reaches our server only with the email you are sending, is used for that one request, and is never stored or logged.</li>
          <li>We keep the time each email was sent and Gmail&apos;s id for it, so the draft shows as sent and can&apos;t go twice.</li>
          <li>You can withdraw the permission at any time in your <a href="https://myaccount.google.com/permissions">Google account settings</a>.</li>
        </ul>
        <p>
          TasteRoute&apos;s use and transfer to any other app of information received from Google APIs will adhere to the{" "}
          <a href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User Data Policy</a>, including the Limited Use requirements.
        </p>
      </section>

      <section className="stack-s">
        <h2 className="h2">Venue contacts</h2>
        <p>
          We only collect business email addresses that venues publish themselves: on their own website, their OpenStreetMap listing, or a public page about them.
          We never guess or build an address. Every draft carries an opt-out line, and anyone on your do-not-contact list is never looked up, drafted or exported again.
          A venue that wants its address removed can write to <Contact />.
        </p>
      </section>

      <section className="stack-s">
        <h2 className="h2">Who we share data with</h2>
        <p>Only what each service needs to do its part. We don&apos;t sell data.</p>
        <ul>
          <li><strong>Qloo</strong>: your brand and product names, the city and venue types, to rank venues by taste.</li>
          <li><strong>Ollama Cloud</strong> (the AI model and web search): your brand profile and the facts about each venue, to write drafts; venue names and cities, to search for a published email.</li>
          <li><strong>OpenStreetMap services</strong> (Nominatim, Photon, Overpass): the places and cities you search for.</li>
          <li><strong>Hunter</strong>, only if enabled: venue website domains, to find published business emails.</li>
          <li><strong>Venue and brand websites</strong>: our server visits the pages it reads, like a browser would.</li>
          <li><strong>Supabase</strong> (database and sign-in), <strong>Google</strong> (sign-in and sending), and our hosting providers.</li>
          <li><strong>Map tiles</strong> (OpenFreeMap, OpenStreetMap) load straight into your browser, so those servers see your IP address.</li>
        </ul>
      </section>

      <section className="stack-s">
        <h2 className="h2">How long we keep it</h2>
        <p>
          Your work stays until you ask us to delete it. Logging out doesn&apos;t delete anything. To see, correct or delete your data, write to <Contact />;
          deleting a workspace removes its runs, contacts, drafts and do-not-contact list.
        </p>
      </section>

      <section className="stack-s">
        <h2 className="h2">Changes and contact</h2>
        <p>
          TasteRoute is for businesses, not for children. If this policy changes, we update the date above. Questions: <Contact />. See also the <Link href="/terms">terms of service</Link>.
        </p>
      </section>
    </div>
  );
}
