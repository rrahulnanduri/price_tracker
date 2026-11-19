import { useEffect, useState } from "react";

export const INTRO_DURATION_MS = 2400;
const FADE_START_MS = 1800;

export function useIntro() {
  const [visible, setVisible] = useState(true);
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const fadeTimer = setTimeout(() => setFading(true), FADE_START_MS);
    const removeTimer = setTimeout(() => setVisible(false), INTRO_DURATION_MS);
    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(removeTimer);
    };
  }, []);

  return { visible, fading };
}

export function IntroLoader({ fading }: { fading: boolean }) {
  return (
    <div className={`intro-screen ${fading ? "fade-out" : ""}`}>
      <div className="loader" />
      <div className="text-[10px] tracking-[0.3em] text-[#46494C] opacity-60 uppercase">
        INITIALIZING
      </div>
    </div>
  );
}
