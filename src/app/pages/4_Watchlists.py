"""Watchlist management — create, browse, and delete named subsets of the universe."""

import streamlit as st

from src.app import queries
from src.app import sidebar as app_sidebar
from src.ticker_input import parse_ticker_input
from src.watchlist import create_watchlist, delete_watchlist, get_membership, replace_membership

st.set_page_config(page_title="Watchlists", layout="wide")


@st.cache_resource
def _get_con():
    return queries.open_warehouse()


def _clear_cache() -> None:
    st.cache_data.clear()


@st.dialog("Edit Watchlist", width="large")
def _edit_dialog(con, wid: int, name: str, current_members: list[str]) -> None:
    st.subheader(name)
    st.caption("Edit the ticker list — one ticker per line.")
    raw_text = st.text_area(
        "Members",
        value="\n".join(current_members),
        height=300,
        key=f"edit_text_{wid}",
    )
    uploaded = st.file_uploader("Or replace with a .txt file", type=["txt"], key=f"edit_file_{wid}")
    if uploaded is not None:
        raw_text = uploaded.read().decode()
    if st.button("Save", key=f"edit_save_{wid}"):
        tickers = parse_ticker_input(raw_text)
        if not tickers:
            st.error("Provide at least one ticker.")
        else:
            try:
                replace_membership(con, wid, tickers)
                _clear_cache()
                st.toast(f"Updated '{name}' with {len(tickers)} ticker(s).")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def main() -> None:
    con = _get_con()

    app_sidebar.watchlist_selector(con)

    st.title("Watchlists")

    watchlists = queries.list_watchlists(con)

    # ---- Create new watchlist ----
    with st.expander("Create new watchlist", expanded=watchlists.empty):
        name_input = st.text_input("Name", key="wl_name_input")
        desc_input = st.text_input("Description (optional)", key="wl_desc_input")
        raw_text = st.text_area("Tickers (one per line)", height=120, key="wl_tickers_text")
        uploaded = st.file_uploader("Or upload a .txt file", type=["txt"], key="wl_file_upload")
        if uploaded is not None:
            raw_text = uploaded.read().decode()

        if st.button("Create watchlist", key="wl_create_btn"):
            name = name_input.strip()
            if not name:
                st.error("Name is required.")
            else:
                tickers = parse_ticker_input(raw_text)
                if not tickers:
                    st.error("Provide at least one ticker.")
                else:
                    try:
                        create_watchlist(con, name, tickers, desc_input.strip() or None)
                        st.success(f"Created '{name}' with {len(tickers)} ticker(s).")
                        _clear_cache()
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

    if watchlists.empty:
        st.info("No watchlists yet. Create one above.")
        return

    st.markdown("---")
    st.subheader("Existing Watchlists")

    for _, row in watchlists.iterrows():
        wid = int(row["watchlist_id"])
        count = int(row["member_count"])
        label = f"{row['name']} ({count} member{'s' if count != 1 else ''})"

        with st.expander(label):
            st.caption(f"Created: {row['created_at']}")
            if row["description"]:
                st.caption(row["description"])

            members = get_membership(con, wid)
            if members:
                st.write(", ".join(members))
            else:
                st.info("No members.")

            col_edit, col_del, _ = st.columns([1, 1, 4])
            with col_edit:
                if st.button("Edit", key=f"edit_wl_{wid}"):
                    _edit_dialog(con, wid, row["name"], members)
            with col_del:
                if st.button("Delete", key=f"del_wl_{wid}", type="secondary"):
                    delete_watchlist(con, wid)
                    if st.session_state.get("active_watchlist_id") == wid:
                        st.session_state["active_watchlist_id"] = None
                    _clear_cache()
                    st.rerun()


main()
