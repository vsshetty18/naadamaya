import { cn } from '@/utils/cn'

/**
 * The hero scene behind the header on every page.
 *
 * Layers, back to front:
 *   1. warm ivory glow across the full width
 *   2. soft drapes, blossoms, bamboo flute, peacock feather (SVG, bottom-left)
 *   3. floating leaves (gentle drift)
 *   4. the tagline "Soul Therapy." with a small lotus divider (right)
 *   5. a fade into the page background, so no hard edge shows under the hero
 *
 * Props:
 *   tagline   the line at the right, "Soul Therapy." by default
 *   src       optional image URL. When given, it replaces the drawn SVG scene,
 *             so a real exported hero PNG can be dropped in without other changes.
 *
 * It is purely decorative: hidden from screen readers and never clickable.
 * Only one is rendered at a time (inside Header), so the fixed gradient ids are safe.
 */

function Lotus({ className }) {
  return (
    <svg viewBox="0 0 40 24" className={className} aria-hidden="true">
      <g fill="#EBD3A0" stroke="#B98A42" strokeWidth="0.9" strokeLinejoin="round">
        <path d="M20 4 C24 9 24 15 20 20 C16 15 16 9 20 4 Z" />
        <path d="M20 20 C15 19 10 15 9 9 C14 10 18 13 20 20 Z" />
        <path d="M20 20 C25 19 30 15 31 9 C26 10 22 13 20 20 Z" />
        <path d="M20 20 C13 21 6 19 3 14 C9 13 15 15 20 20 Z" opacity="0.8" />
        <path d="M20 20 C27 21 34 19 37 14 C31 13 25 15 20 20 Z" opacity="0.8" />
      </g>
    </svg>
  )
}

const LEAVES = [
  { x: 322, y: 34, s: 1, r: 25, delay: '0s' },
  { x: 372, y: 92, s: 1.25, r: -35, delay: '1.4s' },
  { x: 268, y: 22, s: 0.8, r: 60, delay: '2.6s' },
  { x: 396, y: 168, s: 1, r: 140, delay: '0.8s' },
]

function Scene() {
  return (
    <svg
      viewBox="0 0 420 260"
      preserveAspectRatio="xMinYMax meet"
      className="h-full w-auto max-w-none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="hero-drape" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#F3E4C8" />
          <stop offset="1" stopColor="#FBF5E9" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="hero-drape-2" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" stopOpacity="0.9" />
          <stop offset="1" stopColor="#F1E2C6" stopOpacity="0.2" />
        </linearGradient>
        <linearGradient id="hero-bamboo" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#E9C88F" />
          <stop offset="0.55" stopColor="#C99A5B" />
          <stop offset="1" stopColor="#9A6A3A" />
        </linearGradient>
        <linearGradient id="hero-feather" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#8FA070" />
          <stop offset="1" stopColor="#5F7F55" />
        </linearGradient>
      </defs>

      {/* Soft drapes */}
      <path
        d="M0 205 C55 150 115 175 170 140 C222 108 262 150 310 178 L310 260 L0 260 Z"
        fill="url(#hero-drape)"
      />
      <path
        d="M0 232 C70 196 130 214 190 190 C240 170 280 196 330 214 L330 260 L0 260 Z"
        fill="url(#hero-drape-2)"
      />

      {/* Blossoms */}
      <g transform="translate(34 158)">
        {[0, 72, 144, 216, 288].map((a) => (
          <ellipse
            key={a}
            cx="0"
            cy="-10"
            rx="7.5"
            ry="10"
            fill="#FFFDF8"
            stroke="#EADBC0"
            strokeWidth="0.8"
            transform={`rotate(${a})`}
          />
        ))}
        <circle r="4" fill="#E2B865" />
      </g>
      <g transform="translate(66 176) scale(0.72)">
        {[0, 72, 144, 216, 288].map((a) => (
          <ellipse
            key={a}
            cx="0"
            cy="-10"
            rx="7.5"
            ry="10"
            fill="#FFFDF8"
            stroke="#EADBC0"
            strokeWidth="0.8"
            transform={`rotate(${a})`}
          />
        ))}
        <circle r="4" fill="#E2B865" />
      </g>
      <path d="M52 200 C64 190 80 188 92 194 C80 204 64 206 52 200 Z" fill="#A9BF9A" opacity="0.7" />
      <path d="M10 196 C22 186 36 186 46 192 C36 202 22 204 10 196 Z" fill="#A9BF9A" opacity="0.55" />

      {/* Bamboo flute */}
      <g transform="rotate(-9 130 190)">
        <rect x="18" y="182" width="248" height="17" rx="8.5" fill="url(#hero-bamboo)" />
        <rect x="22" y="185" width="240" height="3" rx="1.5" fill="#FFFFFF" opacity="0.35" />
        {/* bands */}
        <rect x="32" y="182" width="5" height="17" fill="#6B4327" />
        <rect x="43" y="182" width="3" height="17" fill="#6B4327" opacity="0.8" />
        <rect x="236" y="182" width="5" height="17" fill="#6B4327" />
        <rect x="247" y="182" width="3" height="17" fill="#6B4327" opacity="0.8" />
        {/* finger holes */}
        {[150, 170, 190, 210].map((cx) => (
          <circle key={cx} cx={cx} cy="190.5" r="2.7" fill="#6B4327" />
        ))}
      </g>

      {/* Peacock feather (local origin = centre of the eye) */}
      <g transform="translate(292 92) rotate(28)">
        <path
          d="M0 62 C-6 90 -22 112 -34 132"
          fill="none"
          stroke="#7E9066"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <path
          d="M0 -72 C40 -42 38 26 0 64 C-38 26 -40 -42 0 -72 Z"
          fill="url(#hero-feather)"
          opacity="0.88"
        />
        {/* barbs */}
        <g stroke="#FBF5E9" strokeWidth="0.7" strokeLinecap="round" opacity="0.45">
          <path d="M0 40 L-24 26" />
          <path d="M0 30 L26 14" />
          <path d="M0 50 L-16 42" />
          <path d="M0 -40 L-20 -50" />
          <path d="M0 -50 L18 -58" />
        </g>
        <ellipse cx="0" cy="-4" rx="21" ry="31" fill="#E9C88F" />
        <ellipse cx="0" cy="-4" rx="13" ry="21" fill="#4C8A88" opacity="0.9" />
        <ellipse cx="0" cy="-3" rx="8.5" ry="14" fill="#1F5F73" />
        <ellipse cx="-2" cy="-9" rx="2.6" ry="4.2" fill="#FFFFFF" opacity="0.35" />
      </g>

      {/* Floating leaves */}
      {LEAVES.map((leaf, i) => (
        <g key={i} transform={`translate(${leaf.x} ${leaf.y}) rotate(${leaf.r}) scale(${leaf.s})`}>
          <g className="animate-float-slow" style={{ animationDelay: leaf.delay }}>
            <path d="M0 -9 C8 -5 8 5 0 10 C-8 5 -8 -5 0 -9 Z" fill="#EBD3A0" opacity="0.7" />
            <path d="M0 -7 L0 8" stroke="#DDBB78" strokeWidth="0.7" opacity="0.7" />
          </g>
        </g>
      ))}
    </svg>
  )
}

export default function HeroArt({ tagline = 'Soul Therapy.', src, className }) {
  return (
    <div className={cn('pointer-events-none select-none', className)} aria-hidden="true">
      {/* 1. Full-width warm glow */}
      <div className="absolute inset-0 bg-hero-glow" />

      {/* Content is kept in the same centred column as the page */}
      <div className="relative mx-auto h-full w-full max-w-desktop">
        {/* 2 + 3. Scene, bottom-left */}
        <div className="absolute bottom-0 left-[-6%] h-full sm:left-0">
          {src ? (
            <img src={src} alt="" className="h-full w-auto max-w-none object-contain" draggable="false" />
          ) : (
            <Scene />
          )}
        </div>

        {/* 4. Tagline, right */}
        <div className="absolute bottom-14 right-4 flex flex-col items-center md:bottom-20 md:right-10">
          <p className="font-serif text-[1.85rem] font-normal leading-none text-brown-700 sm:text-4xl md:text-5xl">
            {tagline}
          </p>
          <div className="mt-3 flex items-center gap-2 md:mt-4">
            <span className="h-px w-10 bg-gradient-to-r from-transparent to-gold-300 md:w-16" />
            <Lotus className="h-4 w-6 md:h-5 md:w-8" />
            <span className="h-px w-10 bg-gradient-to-l from-transparent to-gold-300 md:w-16" />
          </div>
        </div>
      </div>

      {/* 5. Fade into the page so there is no hard edge */}
      <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-ivory to-transparent" />
    </div>
  )
}
