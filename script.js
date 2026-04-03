document.addEventListener('DOMContentLoaded',function(){
    document.querySelectorAll('.toggle-password').forEach(btn=>{
        btn.addEventListener('click',function(){
            const target=document.getElementById(this.dataset.target);
            const icon=this.querySelector('i');
            if(target.type==='password'){target.type='text';icon.classList.remove('fa-eye');icon.classList.add('fa-eye-slash');}
            else{target.type='password';icon.classList.remove('fa-eye-slash');icon.classList.add('fa-eye');}
        });
    });
    setTimeout(()=>{document.querySelectorAll('.alert').forEach(alert=>{new bootstrap.Alert(alert).close();});},3000);
});