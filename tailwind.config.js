/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    screens: {
      // Mobile-first: base = phones (Android / iPhone)
      sm: '480px',   // large phones
      md: '768px',   // tablets
      lg: '1024px',  // small desktop / landscape tablet
      xl: '1280px',  // desktop
    },
    extend: {
      colors: {
        // Backgrounds (warm ivory / cream)
        ivory: {
          DEFAULT: '#FDFAF4',
          50: '#FFFDF9',
          100: '#FBF6EC',
          200: '#F5EDDD',
          300: '#EDE1CB',
        },
        // Typography and primary CTA (earthy browns)
        brown: {
          50: '#F8EFE8',
          100: '#F0DDCF',
          200: '#E2C0A6',
          300: '#C99A78',
          400: '#AE7549',
          500: '#93582F', // REPORT button, Pro button
          600: '#7A4726',
          700: '#5E3720',
          800: '#45291A',
          900: '#301C12', // headings ("Learn", "Report", "Stage")
        },
        // Soft gold accents
        gold: {
          50: '#FBF5E8',
          100: '#F6E9CC',
          200: '#EBD3A0',
          300: '#DDBB78',
          400: '#CDA35B',
          500: '#B98A42', // crown, sparkles
        },
        // Muted sage / green (progress, positive insights, Free plan)
        sage: {
          50: '#F1F5EE',
          100: '#E3EBDD',
          200: '#CBD9C1',
          300: '#A9BF9A',
          400: '#84A075',
          500: '#5F7F55', // credit bar, score ring
          600: '#4B6644',
        },
        // Very subtle blue (Original card, Go plan, rhythm)
        mist: {
          50: '#F0F6F8',
          100: '#E3EFF2',
          200: '#CCE1E7',
          300: '#A3C8D2',
          400: '#5B9AAC',
          500: '#2F7186', // Upload text, Go button
          600: '#255C6E',
        },
        // Peach / blush (Record button, Improvement insights)
        blush: {
          50: '#FCF3EE',
          100: '#F8E7DD',
          200: '#F1D3C2',
          300: '#E6B49A',
        },
        // Semantic metric accents (used by DynamicMetricCard)
        metric: {
          pitch: '#5F7F55',
          rhythm: '#2F7186',
          stability: '#C0892F',
          expression: '#C4574F',
          pronunciation: '#5F9A6A',
          breath: '#8A6BB0',
          ornament: '#B0703F',
        },
        // Status colors for report states
        status: {
          good: '#5F7F55',
          warn: '#D9862F',
          bad: '#C4574F',
        },
      },

      fontFamily: {
        // Elegant serif headings
        serif: ['"Cormorant Garamond"', '"Playfair Display"', 'Georgia', 'serif'],
        // Clean modern supporting text
        sans: ['"DM Sans"', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        // Thin geometric wordmark (NAADAMAYA + tagline)
        display: ['"Jost"', '"DM Sans"', 'sans-serif'],
      },

      fontSize: {
        // Page titles ("Learn", "Report", "Stage")
        'title': ['2.75rem', { lineHeight: '1', letterSpacing: '-0.01em' }],
        'title-lg': ['3.5rem', { lineHeight: '1', letterSpacing: '-0.015em' }],
        'score': ['3.25rem', { lineHeight: '1' }],
      },

      letterSpacing: {
        wordmark: '0.28em',
        tagline: '0.32em',
        cta: '0.3em',
      },

      borderRadius: {
        card: '1.25rem',
        pill: '9999px',
        xl2: '1.5rem',
        xl3: '2rem',
      },

      boxShadow: {
        // Soft, warm, low-contrast (never harsh grey)
        soft: '0 2px 14px rgba(120, 84, 50, 0.07)',
        card: '0 4px 24px rgba(120, 84, 50, 0.09)',
        lifted: '0 10px 36px rgba(120, 84, 50, 0.14)',
        nav: '0 -2px 30px rgba(120, 84, 50, 0.10)',
        cta: '0 8px 22px rgba(147, 88, 47, 0.32)',
        inset: 'inset 0 1px 2px rgba(120, 84, 50, 0.06)',
      },

      backgroundImage: {
        'hero-glow':
          'radial-gradient(120% 90% at 20% 0%, #F6EBD6 0%, #FBF5E9 45%, #FDFAF4 100%)',
        'card-warm': 'linear-gradient(180deg, #FFFEFB 0%, #FCF7EE 100%)',
        'cta-brown': 'linear-gradient(180deg, #A0623A 0%, #8A5230 100%)',
        'pro-glow': 'linear-gradient(180deg, #FFFBF3 0%, #FBF0E0 100%)',
      },

      maxWidth: {
        app: '30rem',     // 480px: phone-shaped column
        tablet: '46rem',  // 736px
        desktop: '72rem', // 1152px
      },

      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        slideUp: {
          '0%': { transform: 'translateY(100%)' },
          '100%': { transform: 'translateY(0)' },
        },
        floatSlow: {
          '0%, 100%': { transform: 'translateY(0) rotate(0deg)' },
          '50%': { transform: 'translateY(-6px) rotate(3deg)' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.7', transform: 'scale(1.06)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        recordPulse: {
          '0%': { boxShadow: '0 0 0 0 rgba(196, 87, 79, 0.45)' },
          '100%': { boxShadow: '0 0 0 22px rgba(196, 87, 79, 0)' },
        },
        barGrow: {
          '0%': { transform: 'scaleX(0)' },
          '100%': { transform: 'scaleX(1)' },
        },
      },

      animation: {
        'fade-up': 'fadeUp 0.5s ease-out both',
        'fade-in': 'fadeIn 0.4s ease-out both',
        'scale-in': 'scaleIn 0.25s ease-out both',
        'slide-up': 'slideUp 0.32s cubic-bezier(0.22, 1, 0.36, 1) both',
        'float-slow': 'floatSlow 6s ease-in-out infinite',
        'pulse-soft': 'pulseSoft 2s ease-in-out infinite',
        'shimmer': 'shimmer 2.2s linear infinite',
        'record-pulse': 'recordPulse 1.4s ease-out infinite',
        'bar-grow': 'barGrow 0.9s cubic-bezier(0.22, 1, 0.36, 1) both',
      },
    },
  },
  plugins: [],
}
