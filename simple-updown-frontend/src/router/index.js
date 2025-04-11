import { createRouter, createWebHistory } from "vue-router";
import FileUpload from "../components/FileUpload.vue";
import FilesList from "../components/FilesList.vue";

const routes = [
    {
        path: '/',
        name: 'FileUpload',
        component: FileUpload
    },
    {
        path: '/files',
        name: 'FilesList',
        component: FilesList
    }
];

const router = createRouter({
    history: createWebHistory(process.env.BASE_URL),
    routes
});

export default router;