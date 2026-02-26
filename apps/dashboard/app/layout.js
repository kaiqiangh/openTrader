import "./globals.css";

export const metadata = {
  title: "OpenTrader Dashboard",
  description: "Operator dashboard for OpenTrader runtime",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
