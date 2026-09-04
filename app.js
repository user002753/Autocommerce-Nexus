const products = [
  {sku:'PHONE-X1',name:'Nexus Phone X1',category:'Electronics',price:29999,cost:24000,stock:50,icon:'▣',color:'#b2b2b2'},
  {sku:'WRLSS-BUD',name:'BassCore Wireless Buds',category:'Audio',price:4999,cost:2800,stock:200,icon:'◉',color:'#e0c2b5'},
  {sku:'CHRG-65W',name:'TurboCharge 65W Adapter',category:'Accessories',price:1999,cost:1100,stock:500,icon:'ϟ',color:'#e7d49a'},
  {sku:'CASE-X1',name:'ArmorCase for Phone X1',category:'Accessories',price:1499,cost:450,stock:300,icon:'▤',color:'#c1d2c3'},
  {sku:'SCRN-GLS',name:'Tempered Glass Shield',category:'Accessories',price:899,cost:250,stock:400,icon:'◇',color:'#a9c4cc'},
  {sku:'LAP-PRO14',name:'ProBook Laptop 14',category:'Electronics',price:74999,cost:62000,stock:20,icon:'▱',color:'#c8bfd6'},
  {sku:'MOUSE-RGB',name:'GripMaster RGB Mouse',category:'Accessories',price:2999,cost:1400,stock:150,icon:'◒',color:'#d3b9b3'},
  {sku:'HDMI-2M',name:'HDMI 2.1 Cable',category:'Accessories',price:1299,cost:350,stock:250,icon:'⌇',color:'#b8c7e1'},
  {sku:'WARR-1Y',name:'Extended Warranty',category:'Services',price:2499,cost:500,stock:9999,icon:'✦',color:'#dac79c'},
  {sku:'SNEAK-R1',name:'FlexRun Sneakers R1',category:'Footwear',price:4999,cost:2200,stock:80,icon:'◒',color:'#d1bdb0'},
  {sku:'SOCKS-BLU',name:'Blue Running Socks (2-pack)',category:'Apparel',price:299,cost:120,stock:100,icon:'🧦',color:'#93c5fd'},
  {sku:'RICE-BAS',name:'Basmati Rice 1kg',category:'Groceries',price:180,cost:120,stock:150,icon:'🌾',color:'#fef08a'},
  {sku:'SALT-TATA',name:'Tata Salt 1kg',category:'Groceries',price:28,cost:18,stock:300,icon:'🧂',color:'#e2e8f0'},
  {sku:'DAL-TUR',name:'Premium Toor Dal 1kg',category:'Groceries',price:160,cost:110,stock:200,icon:'🫘',color:'#fde047'},
  {sku:'KEYBD-MECH',name:'MechType RGB Keyboard',category:'Electronics',price:4499,cost:2800,stock:60,icon:'⌨',color:'#cbd5e1'}
];

const state = { cart: [], filter: 'All', query: '', activeProduct: null };
const money = n => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n);
const byId = id => document.getElementById(id);
const margin = p => ((p.price - p.cost) / p.price) * 100;

function safeShowModal(dialogId) {
  const dialog = typeof dialogId === 'string' ? document.getElementById(dialogId) : dialogId;
  if (!dialog) return;
  try {
    if (dialog.open) {
      if (typeof dialog.close === 'function') dialog.close();
      dialog.removeAttribute('open');
    }
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
  } catch (err) { dialog.setAttribute('open', ''); }
}
window.safeShowModal = safeShowModal;

function safeCloseModal(dialogId) {
  const dialog = typeof dialogId === 'string' ? document.getElementById(dialogId) : dialogId;
  if (!dialog) return;
  try {
    if (typeof dialog.close === 'function') dialog.close();
  } catch (err) {}
  dialog.removeAttribute('open');
}
window.safeCloseModal = safeCloseModal;

function renderProducts() {
  const visible = products.filter(p => (state.filter === 'All' || p.category === state.filter) && `${p.name} ${p.category} ${p.sku}`.toLowerCase().includes(state.query));
  byId('products').innerHTML = visible.map(p => `
    <article class="product">
      <div class="product-image" data-icon="${p.icon}" style="--product-color:${p.color}">
        <span class="product-tag">${p.stock} IN STOCK</span>
      </div>
      <div class="product-info">
        <span class="product-category">${p.category.toUpperCase()} / ${p.sku}</span>
        <h3>${p.name}</h3>
      </div>
      <div class="product-bottom">
        <span class="price">${money(p.price)}</span>
        <button class="add" onclick="openNegotiation('${p.sku}')" aria-label="Negotiate ${p.name}">+</button>
      </div>
    </article>`).join('') || '<p>No products match your search.</p>';
}

function renderFilters() {
  const cats = ['All', ...new Set(products.map(p => p.category))];
  byId('filters').innerHTML = cats.map(c => `<button class="${state.filter === c ? 'active' : ''}" onclick="setFilter('${c}')">${c}</button>`).join('');
}

function setFilter(f) { state.filter = f; renderFilters(); renderProducts(); }
window.setFilter = setFilter;

function openNegotiation(sku) {
  state.activeProduct = products.find(p => p.sku === sku);
  const p = state.activeProduct;
  byId('negotiationName').textContent = p.name;
  byId('listPrice').textContent = money(p.price);
  const max = Math.floor(Math.max(0, margin(p) - 15));
  byId('discountRange').max = Math.max(1, Math.min(30, max || 1));
  byId('discountRange').value = Math.min(10, max || 1);
  byId('maxDiscount').textContent = `${max}%`;
  updateOffer();
  byId('negotiationResult').textContent = '';
  safeShowModal('negotiationModal');
}
window.openNegotiation = openNegotiation;

function updateOffer() {
  const p = state.activeProduct, d = Number(byId('discountRange').value);
  byId('discountOutput').textContent = `${d}%`;
  byId('offerPrice').textContent = money(p.price * (1 - d / 100));
}

function addToCart(p, discount) {
  const item = state.cart.find(i => i.sku === p.sku && i.discount === discount);
  if (item) item.qty++;
  else state.cart.push({ ...p, discount, qty: 1 });
  renderCart();
  showToast(`${p.name} reserved in your transaction`);
}

function renderCart() {
  const subtotal = state.cart.reduce((sum, i) => sum + i.price * (1 - i.discount / 100) * i.qty, 0);
  const protectedAmount = state.cart.reduce((sum, i) => sum + ((i.price * (1 - i.discount / 100)) - i.cost) * i.qty, 0);
  byId('cartCount').textContent = state.cart.reduce((s, i) => s + i.qty, 0);
  byId('subtotal').textContent = money(subtotal);
  byId('protectedMargin').textContent = money(Math.max(0, protectedAmount));
  byId('bundleValue').textContent = money(state.cart.reduce((s, i) => s + i.price * i.discount / 100 * i.qty, 0));
  byId('cartEmpty').style.display = state.cart.length ? 'none' : 'block';
  byId('cartItems').innerHTML = state.cart.map((i, index) => `
    <div class="cart-item">
      <div>
        <h3>${i.name}</h3>
        <p>${i.discount}% NEXUS OFFER · ${money(i.price * (1 - i.discount / 100))}</p>
        <div class="item-actions">
          <button onclick="changeQty(${index},-1)">−</button>
          <span>${i.qty}</span>
          <button onclick="changeQty(${index},1)">+</button>
        </div>
      </div>
      <b>${money(i.price * (1 - i.discount / 100) * i.qty)}</b>
    </div>`).join('');
  byId('marginNote').textContent = state.cart.length ? `Margin protocol remains protected above the 15% merchant floor.` : 'Your order is protected by the Nexus margin protocol.';
}

function changeQty(index, n) {
  state.cart[index].qty += n;
  if (state.cart[index].qty < 1) state.cart.splice(index, 1);
  renderCart();
}
window.changeQty = changeQty;

function showCart(open = true) {
  byId('cart').classList.toggle('open', open);
  byId('backdrop').classList.toggle('show', open);
  byId('cart').setAttribute('aria-hidden', String(!open));
}

function showToast(message) {
  const t = byId('toast');
  t.textContent = message;
  t.classList.add('show');
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(() => t.classList.remove('show'), 2800);
}
window.showToast = showToast;

byId('discountRange').addEventListener('input', updateOffer);
byId('acceptOffer').onclick = () => {
  const p = state.activeProduct, requested = Number(byId('discountRange').value), allowed = Math.max(0, margin(p) - 15), granted = Math.min(requested, allowed);
  if (!granted) { byId('negotiationResult').textContent = 'This item cannot take a discount while keeping the margin floor.'; return; }
  addToCart(p, granted);
  byId('negotiationResult').textContent = `Offer accepted at ${granted.toFixed(0)}%. Inventory is reserved for you.`;
  setTimeout(() => { safeCloseModal('negotiationModal'); showCart(); }, 700);
};

byId('openCart').onclick = () => showCart();
byId('closeCart').onclick = () => showCart(false);
byId('backdrop').onclick = () => showCart(false);
byId('search').oninput = e => { state.query = e.target.value.toLowerCase(); renderProducts(); };

document.querySelectorAll('.modal-close').forEach(b => b.onclick = () => safeCloseModal(b.closest('dialog')));

window.appState = state;
window.showCart = showCart;
window.renderCart = renderCart;

renderFilters();
renderProducts();
renderCart();

