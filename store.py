import streamlit as st
from sqlalchemy import text
import pandas as pd
import json

# Connect to the Cloud Database
conn = st.connection("postgresql", type="sql")

st.set_page_config(page_title="B2B Wholesale Portal", layout="wide", initial_sidebar_state="expanded")

# --- INITIALIZE SHOPPING CART ---
if 'cart' not in st.session_state:
    st.session_state.cart = {}

# --- SIDEBAR: THE FLOATING CART & CHECKOUT ---
with st.sidebar:
    st.title("🛒 Your Order")
    
    if not st.session_state.cart:
        st.info("Your cart is empty. Click on a shirt to start adding stock.")
    else:
        total_items = 0
        total_price = 0.0
        
        for var_id, item in st.session_state.cart.items():
            st.write(f"**{item['name']}**")
            st.write(f"Color: {item['color']} | Size: {item['size']}")
            st.write(f"Qty: {item['qty']} x ₹{item['price']} = ₹{item['qty'] * item['price']}")
            st.markdown("---")
            total_items += item['qty']
            total_price += (item['qty'] * item['price'])
            
        st.success(f"**Total Items:** {total_items}")
        st.success(f"**Estimated Total:** ₹{total_price:,.2f}")
        
        st.markdown("### Checkout Details")
        with st.form("checkout_form"):
            ret_name = st.text_input("Business Name")
            ret_phone = st.text_input("WhatsApp Number")
            submit_order = st.form_submit_button("Submit Order 🚀", use_container_width=True)
            
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
                    st.rerun()
                else:
                    st.error("Please provide Business Name and Phone.")

# --- PRODUCT DIALOG (POP-UP WINDOW) ---
@st.dialog("Product Details")
def show_product(design_id, design_name, price, moq):
    st.subheader(design_name)
    st.write(f"**Price:** ₹{price} per piece | **MOQ:** {moq} pieces")
    
    # Fetch and show Cloudinary images
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
            selected_size = st.selectbox("Select Size", filtered_by_color['size'].unique())
            
        specific_variant = filtered_by_color[filtered_by_color['size'] == selected_size].iloc[0]
        v_id = specific_variant['variant_id']
        current_stock = specific_variant['stock_quantity']
        
        with col2:
            if current_stock == 0:
                st.error("🚫 Out of Stock")
            else:
                st.success(f"📦 {current_stock} available")
        
        st.markdown("---")
        
        if current_stock > 0:
            order_qty = st.number_input("Quantity to Order", min_value=moq, max_value=int(current_stock), step=1)
            
            if st.button("Add to Cart 🛒", use_container_width=True):
                st.session_state.cart[str(v_id)] = {
                    "name": design_name,
                    "color": selected_color,
                    "size": selected_size,
                    "price": float(price),
                    "qty": int(order_qty)
                }
                st.rerun()

# --- MAIN CATALOG: THE GRID VIEW ---
st.title("👔 Wholesale Catalog")
st.write("Browse our latest designs and add stock directly to your cart.")
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
                    # Renders directly from the Cloudinary URL
                    if pd.notna(row['image_url']):
                        st.image(row['image_url'], use_container_width=True)
                    else:
                        st.write("📷 *No Image*")
                    
                    st.write(f"**{row['design_name']}**")
                    st.write(f"₹{row['price']}")
                    
                    if st.button("View Options", key=f"btn_{row['design_id']}_{index}", use_container_width=True):
                        show_product(row['design_id'], row['design_name'], row['price'], row['moq'])

except Exception as e:
    st.error(f"Could not load catalog: {e}")