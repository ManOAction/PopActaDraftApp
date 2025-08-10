import { BrowserRouter, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import WelcomeStrip from "./components/WelcomeStrip";
import Home from "./pages/Home";
import Players from "./pages/Players";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <div className="bg-base-200 min-h-screen">
      <BrowserRouter>
        <Navbar />
        <WelcomeStrip />
        <main className="py-6">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/players" element={<Players />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </BrowserRouter>
    </div>
  );
}
