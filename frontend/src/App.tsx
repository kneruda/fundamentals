import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { DataPage } from "./components/DataPage";
import { FundamentalScreenerPage } from "./features/screener/FundamentalScreenerPage";
import { GenericScreenerPage } from "./features/screener/GenericScreenerPage";
import { CompanyPage } from "./features/company/CompanyPage";
import { WatchlistsPage } from "./features/watchlists/WatchlistsPage";
import { ActiveWatchlistProvider, WatchlistSelector } from "./features/watchlists/ActiveWatchlist";
import { UniversePage } from "./features/universe/UniversePage";
import { SectorsPage } from "./features/sectors/SectorsPage";

export function App() {
  return <BrowserRouter><ActiveWatchlistProvider><nav><strong>Fundamentals</strong><NavLink to="/">Dashboard</NavLink><NavLink to="/company">Company</NavLink><NavLink to="/screens">Screens</NavLink><NavLink to="/forward">Forward</NavLink><NavLink to="/technical">Technical</NavLink><NavLink to="/universe">Universe</NavLink><NavLink to="/watchlists">Watchlists</NavLink><NavLink to="/sectors">Sectors</NavLink><WatchlistSelector/></nav><Routes><Route path="/" element={<DataPage title="Dashboard" copy="Your active universe at a glance." path="dashboard"/>}/><Route path="/company" element={<CompanyPage/>}/><Route path="/screens" element={<FundamentalScreenerPage/>}/><Route path="/forward" element={<GenericScreenerPage family="forward"/>}/><Route path="/technical" element={<GenericScreenerPage family="technical"/>}/><Route path="/universe" element={<UniversePage/>}/><Route path="/watchlists" element={<WatchlistsPage/>}/><Route path="/sectors" element={<SectorsPage/>}/></Routes></ActiveWatchlistProvider></BrowserRouter>;
}
