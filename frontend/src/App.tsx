import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { DataPage } from "./components/DataPage";
import { FundamentalScreenerPage } from "./features/screener/FundamentalScreenerPage";
import { GenericScreenerPage } from "./features/screener/GenericScreenerPage";
import { CompanyPage } from "./features/company/CompanyPage";
import { WatchlistsPage } from "./features/watchlists/WatchlistsPage";
import { UniversePage } from "./features/universe/UniversePage";

export function App() {
  return <BrowserRouter><nav><strong>Fundamentals</strong><NavLink to="/">Dashboard</NavLink><NavLink to="/company">Company</NavLink><NavLink to="/screens">Screens</NavLink><NavLink to="/forward">Forward</NavLink><NavLink to="/technical">Technical</NavLink><NavLink to="/universe">Universe</NavLink><NavLink to="/watchlists">Watchlists</NavLink><NavLink to="/sectors">Sectors</NavLink></nav><Routes><Route path="/" element={<DataPage title="Dashboard" copy="Your active universe at a glance." path="dashboard"/>}/><Route path="/company" element={<CompanyPage/>}/><Route path="/screens" element={<FundamentalScreenerPage/>}/><Route path="/forward" element={<GenericScreenerPage family="forward"/>}/><Route path="/technical" element={<GenericScreenerPage family="technical"/>}/><Route path="/universe" element={<UniversePage/>}/><Route path="/watchlists" element={<WatchlistsPage/>}/><Route path="/sectors" element={<DataPage title="Sectors" copy="Full-universe sector medians." path="sectors"/>}/></Routes></BrowserRouter>;
}
