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
        TasteRoute (&ldquo;we&rdquo;) helps food and drink brands find venues whose guests share their taste, and drafts a first email to each.
        This policy explains what information we collect, including the data we receive from Google, how we use, share, protect and keep it,
        and how you can delete it.
      </p>

      <section className="stack-s">
        <h2 className="h2">In short</h2>
        <ul>
          <li>Logging in is optional. Without it, your work lives in an anonymous workspace in this browser.</li>
          <li>If you log in with Google, we receive your Google account id, email address, name and profile picture, and permission to send email from your Gmail. We cannot read your email.</li>
          <li>We send an email only when you click Send or Send all. Google&apos;s access token is never stored.</li>
          <li>We don&apos;t sell data, show ads, use analytics or tracking cookies, or use your Google data to train AI models.</li>
          <li>You can delete your account and everything in it at any time from the account menu.</li>
        </ul>
      </section>

      <section className="stack-s">
        <h2 className="h2">Information we collect</h2>
        <ul>
          <li><strong>What you give us:</strong> your brand name, products, website address and location, the cities and venue types you choose, edits to drafts, and your do-not-contact list.</li>
          <li><strong>What we create for you:</strong> runs (ranked venues and the reasons), venue contacts, email drafts, and a log of the calls each run made (to Qloo, the AI model and other services) so every result can be traced.</li>
          <li><strong>Technical data:</strong> a workspace token kept in your browser&apos;s local storage, and your IP address, stored only as a salted hash to limit how many runs one visitor can start.</li>
          <li><strong>From Google, if you log in:</strong> described in the next section.</li>
          <li><strong>From public sources:</strong> venue details from Qloo and OpenStreetMap, the text of your website, and business email addresses venues publish themselves.</li>
        </ul>
      </section>

      <section className="stack-s">
        <h2 className="h2">Google user data</h2>
        <h3 className="h3">What we access</h3>
        <ul>
          <li><strong>Google Sign-In</strong> (through our sign-in provider, Supabase Auth): your Google account id, email address, name and profile picture.</li>
          <li><strong>Gmail, send only</strong> (<code>https://www.googleapis.com/auth/gmail.send</code>): permission to send email as you. It gives no access to read, search, delete or label your messages, or to your contacts or settings. Besides this and the basic sign-in scopes (your email address and profile), we request no Google scopes.</li>
          <li><strong>Gmail message ids:</strong> when Gmail sends an email for you, it returns an id for that message, which we store.</li>
        </ul>
        <h3 className="h3">How we use it</h3>
        <ul>
          <li>Your account id and email address sign you in and keep your runs in one workspace across your devices.</li>
          <li>Your name, email and picture are shown to you in the account menu.</li>
          <li>The Gmail permission is used only to send the emails you choose: <strong>Send with Gmail</strong> sends one draft; <strong>Send all</strong> sends the unsent drafts on the page after you confirm how many. Each goes once, exactly as shown, to the address shown. We never send on a schedule or in the background.</li>
          <li>Gmail message ids mark a draft as sent, so it can&apos;t be sent twice.</li>
        </ul>
        <h3 className="h3">How we share it</h3>
        <p>
          We do not sell Google user data or share it with advertisers, data brokers, Qloo, our AI model provider, OpenStreetMap or Hunter.
          Supabase, our sign-in and database provider, stores your account details on our behalf. Your emails pass to Google, which delivers them.
          We would disclose data only if the law requires it.
        </p>
        <h3 className="h3">How we store and protect it</h3>
        <ul>
          <li>Your account id and email are stored in our database at Supabase (Tokyo region). Supabase Auth keeps your Google id, email, name and picture.</li>
          <li>Google&apos;s access token for sending stays in your browser for about an hour. It reaches our server over HTTPS only with an email you are sending, is used for that request, and is never written to our database, files or logs.</li>
          <li>All traffic uses HTTPS (TLS). Supabase encrypts stored data. Only our API server can connect to the database, with a secret credential; row-level security blocks every public route into it. Secret keys never reach the browser.</li>
        </ul>
        <h3 className="h3">How long we keep it, and how to delete it</h3>
        <ul>
          <li>We keep your account data while you have an account.</li>
          <li><strong>Delete account and data</strong> in the account menu deletes your account, your Google identity at Supabase, and all your runs, contacts, drafts and do-not-contact list, immediately and for good.</li>
          <li>You can also ask us to delete it by writing to <Contact />; we do so within 30 days.</li>
          <li>You can withdraw TasteRoute&apos;s access to your Google account at any time at <a href="https://myaccount.google.com/permissions">myaccount.google.com/permissions</a>. After that we cannot send email for you.</li>
        </ul>
        <h3 className="h3">Limited Use</h3>
        <p>
          TasteRoute&apos;s use and transfer to any other app of information received from Google APIs will adhere to the{" "}
          <a href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User Data Policy</a>, including the Limited Use requirements. In particular:
        </p>
        <ul>
          <li>We use Google user data only to provide the features described above, which you can see and use in the app.</li>
          <li>We don&apos;t transfer it to others, except as needed to provide those features, to comply with the law, or as part of a merger or sale with notice to you.</li>
          <li>We don&apos;t use it for advertising, including retargeting, personalised or interest-based ads.</li>
          <li>No person reads it, unless you ask us to, it is needed for security or to investigate abuse, or the law requires it.</li>
          <li>We do not use Google Workspace API data, including Gmail data, to develop, improve or train generalised or non-personalised AI or machine-learning models.</li>
        </ul>
      </section>

      <section className="stack-s">
        <h2 className="h2">How we use other information</h2>
        <p>
          To rank venues, find published contacts, write drafts, keep the service working and fair (rate limits), and trace how each result was produced.
          We don&apos;t use it for advertising, and we don&apos;t sell it.
        </p>
      </section>

      <section className="stack-s">
        <h2 className="h2">Service providers</h2>
        <p>Each gets only what it needs for its part.</p>
        <ul>
          <li><strong>Qloo</strong>: your brand and product names, the city and venue types, to rank venues by taste.</li>
          <li><strong>Ollama Cloud</strong> (AI model and web search): your brand profile and facts about each venue, to write drafts; venue names and cities, to search for a published email.</li>
          <li><strong>OpenStreetMap services</strong> (Nominatim, Photon, Overpass): the places and cities you search for.</li>
          <li><strong>Hunter</strong>, only if enabled: venue website domains, to find published business emails.</li>
          <li><strong>Venue and brand websites</strong>: our server visits the pages it reads, like a browser would.</li>
          <li><strong>Supabase</strong> (database and sign-in), <strong>Google</strong> (sign-in and sending), <strong>Render</strong> and <strong>Vercel</strong> (hosting).</li>
          <li><strong>Map tiles</strong> (OpenFreeMap, OpenStreetMap) load straight into your browser, so those servers see your IP address.</li>
        </ul>
      </section>

      <section className="stack-s">
        <h2 className="h2">Cookies and local storage</h2>
        <p>
          We use no cookies for tracking. Your browser&apos;s local storage holds your workspace token and, when you log in, your sign-in session and
          Google&apos;s short-lived sending token. Logging out clears them.
        </p>
      </section>

      <section className="stack-s">
        <h2 className="h2">Venue contacts</h2>
        <p>
          We collect only business email addresses that venues publish themselves: on their own website, their OpenStreetMap listing, or a public page about them.
          We never guess or build an address. Every draft carries an opt-out line, and anyone on a do-not-contact list is never looked up, drafted, exported or sent to again.
          A venue that wants its address removed can write to <Contact />.
        </p>
      </section>

      <section className="stack-s">
        <h2 className="h2">Your choices and rights</h2>
        <ul>
          <li>Download your runs, contacts and approved drafts as a CSV from any run.</li>
          <li>Delete your account and data from the account menu, or ask us to see, correct or delete your data at <Contact />.</li>
          <li>Without logging in, your work isn&apos;t tied to your identity; to delete it, send us a link to the run.</li>
          <li>Depending on where you live, you may have further rights (for example under the GDPR or CCPA); write to us to use them.</li>
        </ul>
      </section>

      <section className="stack-s">
        <h2 className="h2">Children, changes and contact</h2>
        <p>
          TasteRoute is for businesses and is not directed at children under 16. If this policy changes, we update the date above. Questions: <Contact />. See also the <Link href="/terms">terms of service</Link>.
        </p>
      </section>
    </div>
  );
}
