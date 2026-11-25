import { useEffect, useRef } from "react";
import { animate, useReducedMotion } from "motion/react";

interface AnimatedNumberProps {
  value: number;
  format: (value: number) => string;
  /** Seconds. */
  duration?: number;
  className?: string;
  title?: string;
}

/**
 * A number that counts to its value. It writes to the DOM directly rather than
 * re-rendering on every frame, and shows the final value at once for anyone
 * who prefers reduced motion. Screen readers get only the final value.
 */
export function AnimatedNumber({ value, format, duration = 0.9, className, title }: AnimatedNumberProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const previous = useRef<number | null>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    // First appearance counts up from a little below; later changes count from the old value.
    const from = previous.current ?? value * 0.85;
    previous.current = value;
    if (reduce || from === value) {
      node.textContent = format(value);
      return;
    }
    const controls = animate(from, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (latest) => {
        node.textContent = format(latest);
      },
    });
    return () => controls.stop();
  }, [value, format, duration, reduce]);

  return (
    <span className={className} title={title}>
      <span ref={ref} aria-hidden>
        {format(value)}
      </span>
      <span className="sr-only">{format(value)}</span>
    </span>
  );
}
