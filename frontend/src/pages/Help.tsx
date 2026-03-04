export function Help() {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <h1 className="text-2xl font-semibold text-slate-800">How it works</h1>
      <div className="mt-6 space-y-6 text-sm text-slate-700">
        <section>
          <h2 className="font-semibold text-slate-800">What is the secret phrase?</h2>
          <p className="mt-1">
            A phrase only you know—for example, a sentence that has meaning to you, or a famous phrase. You don&apos;t have to remember the exact words. When you sign in, you describe the <em>idea</em> in your own words (or by speaking it). The system checks that the meaning matches.
          </p>
        </section>
        <section>
          <h2 className="font-semibold text-slate-800">Text or voice?</h2>
          <p className="mt-1">
            You can register and sign in by <strong>typing</strong> or by <strong>speaking</strong>. Voice is useful if you prefer not to type or use a screen reader. You can change between text and voice later in Profile (one type per account at a time).
          </p>
        </section>
        <section>
          <h2 className="font-semibold text-slate-800">Listen to prompt (TTS)</h2>
          <p className="mt-1">
            On the sign-in step you can press &quot;Listen to prompt&quot; to hear the question read aloud. This helps if you can&apos;t or don&apos;t want to read the screen.
          </p>
        </section>
        <section>
          <h2 className="font-semibold text-slate-800">What if I forget my secret?</h2>
          <p className="mt-1">
            If you&apos;re already signed in, go to <strong>Profile</strong> and set a new secret (text or voice). If you can&apos;t sign in, you&apos;ll need to create a new account with a new username or email.
          </p>
        </section>
      </div>
    </div>
  )
}
