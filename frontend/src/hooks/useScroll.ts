import { useEffect, useState } from "react";

/** Page scroll position as 0..1, for the progress bar and the back-to-top button. */
export function useScroll(): { progress: number; scrolled: boolean } {
  const [state, setState] = useState({ progress: 0, scrolled: false });
  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const doc = document.documentElement;
      const max = doc.scrollHeight - window.innerHeight;
      setState({ progress: max > 0 ? Math.min(1, window.scrollY / max) : 0, scrolled: window.scrollY > 600 });
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);
  return state;
}
