/** @type {import('tailwindcss').Config} */
const config = {
  darkMode: ["class"],
  content: [
    './app/**/*.{js,jsx,ts,tsx}',
    './components/**/*.{js,jsx,ts,tsx}',
    './components/ui/**/*.{js,jsx,ts,tsx}',
    './pages/**/*.{js,jsx,ts,tsx}',
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  prefix: "",
  theme: {
  	container: {
  		center: true,
  		padding: '2rem',
  		screens: {
  			'2xl': '1400px'
  		}
  	},
  	extend: {
  		fontFamily: {
  			sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
  			serif: ['var(--font-serif)', 'Georgia', 'serif'],
  		},
  		typography: {
  			DEFAULT: {
  				css: {
  					'--tw-prose-body': 'var(--font-serif)',
  					'--tw-prose-headings': 'var(--font-sans)',
  					fontFamily: 'var(--font-serif)',
  					h1: { fontFamily: 'var(--font-sans)' },
  					h2: { fontFamily: 'var(--font-sans)' },
  					h3: { fontFamily: 'var(--font-sans)' },
  					h4: { fontFamily: 'var(--font-sans)' },
  				},
  			},
  			invert: {
  				css: {
  					'--tw-prose-body': 'var(--font-serif)',
  					'--tw-prose-headings': 'var(--font-sans)',
  				},
  			},
  		},
  		colors: {
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))'
  			},
  			// Unified IntelligenceCard neutral-brand scale + accent. Per-site
  			// palette lives in globals.css (Arc: slate neutrals, slate accent);
  			// the component uses nb-*/icaccent so it stays byte-identical across
  			// stacks. RGB triples + <alpha-value> so /opacity modifiers work.
  			nb: {
  				'50': 'rgb(var(--nb-50) / <alpha-value>)',
  				'100': 'rgb(var(--nb-100) / <alpha-value>)',
  				'200': 'rgb(var(--nb-200) / <alpha-value>)',
  				'300': 'rgb(var(--nb-300) / <alpha-value>)',
  				'400': 'rgb(var(--nb-400) / <alpha-value>)',
  				'500': 'rgb(var(--nb-500) / <alpha-value>)',
  				'600': 'rgb(var(--nb-600) / <alpha-value>)',
  				'700': 'rgb(var(--nb-700) / <alpha-value>)',
  				'800': 'rgb(var(--nb-800) / <alpha-value>)',
  				'900': 'rgb(var(--nb-900) / <alpha-value>)',
  				'950': 'rgb(var(--nb-950) / <alpha-value>)'
  			},
  			icaccent: 'rgb(var(--ic-accent) / <alpha-value>)'
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		keyframes: {
  			'accordion-down': {
  				from: {
  					height: '0'
  				},
  				to: {
  					height: 'var(--radix-accordion-content-height)'
  				}
  			},
  			'accordion-up': {
  				from: {
  					height: 'var(--radix-accordion-content-height)'
  				},
  				to: {
  					height: '0'
  				}
  			}
  		},
  		animation: {
  			'accordion-down': 'accordion-down 0.2s ease-out',
  			'accordion-up': 'accordion-up 0.2s ease-out'
  		}
  	}
  },
  plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
};
export default config;
