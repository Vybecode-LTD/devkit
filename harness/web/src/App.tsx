import { KERNEL_WEB_VERSION } from "@/kernel";

/** The harness's placeholder page until K4 brings the kernel's shell. */
export function App() {
  return (
    <main>
      <h1>DevKit harness</h1>
      <p>Kernel {KERNEL_WEB_VERSION}. The app shell arrives in phase K4.</p>
    </main>
  );
}
