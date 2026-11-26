/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export default function App() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#090D16] p-6 text-slate-100">
      <div className="w-full max-w-2xl rounded-xl border border-slate-800 bg-[#0F1623] p-8">
        <h1 className="font-display text-xl font-semibold text-slate-100">
          Python Terminal Mode Active
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-400">
          The Node/Express web server (<code className="text-sky-300">server.ts</code>) has been removed. Launch the 100% terminal-based Python TUI directly in your shell:
        </p>
        <pre className="mt-4 overflow-x-auto rounded-lg border border-slate-800 bg-[#090D16] p-4 font-mono text-xs text-sky-300">
          python3 Dex-II/main.py
        </pre>
      </div>
    </main>
  );
}
