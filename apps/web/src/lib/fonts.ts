import { Alegreya, Inter, Space_Mono } from "next/font/google";

/** Inter for UI, Space Mono for dates and record locators, Alegreya for stories and headings. */
export const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
export const spaceMono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-space-mono",
  display: "swap",
});
export const alegreya = Alegreya({ subsets: ["latin"], variable: "--font-alegreya", display: "swap" });

export const fontVariables = `${inter.variable} ${spaceMono.variable} ${alegreya.variable}`;
