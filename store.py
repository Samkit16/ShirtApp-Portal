import streamlit as st
from sqlalchemy import text
import pandas as pd
import json
import time

# Connect to Database
conn = st.connection("postgresql", type="sql")

st.set_page_config(page_title="B2B Wholesale Portal", layout="wide")

# --- HIDE STREAMLIT BRANDING ---
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            /* Modern Streamlit specific tags */
            [data-testid="stHeader"] {visibility: hidden !important;}
            [data-testid="stToolbar"] {visibility: hidden !important;}
            [data-testid="stDecoration"] {visibility: hidden !important;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- INITIALIZE SHOPPING CART ---
if 'cart' not in st.session_state:
    st.session_state.cart = {}

# Calculate total items dynamically for the Tab title
total_cart_items = sum(item['qty'] for item in st.session_state.cart.values()) if st.session_state.cart else 0

# --- MOBILE-FRIENDLY TABS ---
tab_shop, tab_cart = st.tabs(["👔 Shop Catalog", f"🛒 Your Cart ({total_cart_items})"])

# --- PRODUCT DIALOG (POP-UP WINDOW) ---
@st.dialog("Product Details")
def show_product(design_id, design_name, price, moq):
    st.subheader(design_name)
    st.write(f"**Price:** ₹{price} per piece | **MOQ:** {moq} pieces")
    
    # Fetch and show images
    images_df = conn.query(f"SELECT image_url FROM shirt_images WHERE design_id = {design_id};", ttl=0)
    if not images_df.empty:
        cols = st.columns(len(images_df))
        for idx, row in images_df.iterrows():
            if pd.notna(row['image_url']):
                cols[idx].image(row['image_url'], use_container_width=True)
    
    # Fetch variants
    variants_df = conn.query(f"SELECT variant_id, color, size, stock_quantity FROM shirt_variants WHERE design_id = {design_id};", ttl=0)
    
    if variants_df.empty:
        st.warning("No stock added for this design yet.")
    else:
        available_colors = variants_df['color'].unique()
        selected_color = st.selectbox("Select Color", available_colors)
        
        filtered_by_color = variants_df[variants_df['color'] == selected_color]
        
        col1, col2 = st.columns(2)
        with col1:
            # S is removed implicitly because it won't be in the database, but we handle options cleanly
            available_sizes = list(filtered_by_color['size'].unique())
            
            # Use multiselect so buyers can select more than one size
            selected_sizes = st.multiselect("Select Size(s)", ["Full Set (All Sizes)"] + available_sizes)
            
        # Determine final sizes based on selection
        if "Full Set (All Sizes)" in selected_sizes:
            final_sizes = available_sizes
            is_full_set = True
            min_stock = int(filtered_by_color['stock_quantity'].min())
        else:
            final_sizes = selected_sizes
            is_full_set = False
            
        with col2:
            if not final_sizes:
                st.info("Choose size(s) to view availability.")
            elif is_full_set:
                if min_stock == 0:
                    st.error("🚫 Broken Set")
                else:
                    st.success(f"📦 {min_stock} full sets available")
            else:
                # Show individual stock check for each selected size
                for sz in final_sizes:
                    sz_stock = filtered_by_color[filtered_by_color['size'] == sz].iloc[0]['stock_quantity']
                    if sz_stock == 0:
                        st.error(f"🚫 Size {sz}: Out of Stock")
                    else:
                        st.text(f"📦 Size {sz}: {sz_stock} available")
        
        st.markdown("---")
        
        if final_sizes:
            if is_full_set and min_stock > 0:
                order_qty = st.number_input("How many full sets?", min_value=1, max_value=min_stock, step=1)
                if st.button("Add Full Set to Cart 🛒", width="stretch"):
                    for _, row in filtered_by_color.iterrows():
                        v_id = row['variant_id']
                        sz = row['size']
                        st.session_state.cart[str(v_id)] = {
                            "name": design_name,
                            "color": selected_color,
                            "size": sz,
                            "price": float(price),
                            "qty": int(order_qty)
                        }
                    st.rerun()
                    
            elif not is_full_set:
                # Enforce individual size ordering quantities
                quantities = {}
                can_order = True
                
                for sz in final_sizes:
                    variant_row = filtered_by_color[filtered_by_color['size'] == sz].iloc[0]
                    v_id = variant_row['variant_id']
                    max_stock = int(variant_row['stock_quantity'])
                    
                    if max_stock > 0:
                        # Allow setting different or uniform amounts per size selected
                        quantities[str(v_id)] = st.number_input(f"Quantity for Size {sz}", min_value=int(moq), max_value=max_stock, value=int(moq), step=1, key=f"qty_{v_id}")
                    else:
                        can_order = False
                
                if can_order and quantities:
                    if st.button("Add Selected Sizes to Cart 🛒", width="stretch"):
                        for v_id_str, qty_to_buy in quantities.items():
                            variant_info = filtered_by_color[filtered_by_color['variant_id'] == int(v_id_str)].iloc[0]
                            st.session_state.cart[v_id_str] = {
                                "name": design_name,
                                "color": selected_color,
                                "size": variant_info['size'],
                                "price": float(price),
                                "qty": int(qty_to_buy)
                            }
                        st.rerun()
# --- TAB 1: THE SHOP CATALOG ---
with tab_shop:
    st.title("👔 Wholesale Catalog")
    st.write("Browse our latest designs and tap to view options.")
    st.markdown("---")

    catalog_query = """
        SELECT d.design_id, d.design_name, d.price, d.moq, 
               (SELECT image_url FROM shirt_images 
                WHERE design_id = d.design_id 
                ORDER BY is_primary DESC, image_id ASC LIMIT 1) as image_url
        FROM shirt_designs d
        WHERE d.is_active = TRUE
        ORDER BY d.design_id DESC;
    """
    try:
        catalog_df = conn.query(catalog_query, ttl=0)
        
        if catalog_df.empty:
            st.info("No active designs in the catalog.")
        else:
            cols = st.columns(4)
            for index, row in catalog_df.iterrows():
                col = cols[index % 4] 
                with col:
                    with st.container(border=True):
                        if pd.notna(row['image_url']):
                            st.image(row['image_url'], use_container_width=True)
                        else:
                            st.write("📷 *No Image*")
                        
                        st.write(f"**{row['design_name']}**")
                        st.write(f"₹{row['price']}")
                        
                        # Pass MOQ into the Dialog function
                        if st.button("View Options", key=f"btn_{row['design_id']}_{index}", width="stretch"):
                            show_product(row['design_id'], row['design_name'], row['price'], row['moq'])

    except Exception as e:
        st.error(f"Could not load catalog: {e}")

# --- TAB 2: THE MOBILE CHECKOUT ---
with tab_cart:
    st.title("🛒 Your Secure Checkout")
    
    if not st.session_state.cart:
        st.info("Your cart is empty. Head back to the Shop tab to add inventory.")
    else:
        total_items = 0
        total_price = 0.0
        
        for var_id, item in st.session_state.cart.items():
            with st.container(border=True):
                st.write(f"**{item['name']}**")
                st.write(f"Color: {item['color']} | Size: {item['size']}")
                st.write(f"Qty: {item['qty']} x ₹{item['price']} = **₹{item['qty'] * item['price']}**")
            
            total_items += item['qty']
            total_price += (item['qty'] * item['price'])
            
        st.success(f"**Total Items:** {total_items}")
        st.success(f"**Estimated Total:** ₹{total_price:,.2f}")
        
        st.markdown("### Finalize Order")
        with st.form("checkout_form"):
            ret_name = st.text_input("Business Name")
            ret_phone = st.text_input("WhatsApp Number")
            submit_order = st.form_submit_button("Submit Order 🚀", width="stretch")
            
            if submit_order:
                if ret_name and ret_phone:
                    cart_json = json.dumps(st.session_state.cart)
                    with conn.session as s:
                        query = text("""
                            INSERT INTO orders (retailer_name, retailer_phone, order_summary, total_value) 
                            VALUES (:name, :phone, :summary, :total)
                        """)
                        s.execute(query, {"name": ret_name, "phone": ret_phone, "summary": cart_json, "total": total_price})
                        s.commit()
                    
                    st.session_state.cart = {}
                    st.success("✅ Order sent successfully! We will contact you soon.")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("⚠️ Please provide your Business Name and Phone number.")
